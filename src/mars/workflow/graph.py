"""LangGraph workflow.

planner ──fan-out──▶ researcher (parallel, one per task) ──▶ analyst ─┬─▶ researcher (follow-up round)
                                                                       ├─▶ approval (optional HITL) ─▶ writer
                                                                       ├─▶ writer ◀──────────┐
                                                                       └─▶ finalize          │
                                                          writer ─▶ critic ─(issues)─────────┘
                                                                       └─(ok / budget out)─▶ finalize
"""

from __future__ import annotations

from urllib.parse import urlsplit

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer
from langgraph.graph import END, START, StateGraph
from langgraph.types import Send, interrupt

from ..agents import analyst, critic, planner, researcher, writer
from ..agents.writer import render_sources
from ..core.usage import usage_var
from ..schemas import Analysis, Report, ResearchTask
from .deps import Deps
from .state import ALLOWED_TYPES, ResearchState


def default_checkpointer() -> MemorySaver:
    return MemorySaver(serde=JsonPlusSerializer(allowed_msgpack_modules=ALLOWED_TYPES))


def _fan_out(tasks: list[ResearchTask], question: str) -> list[Send]:
    return [Send("researcher", {"task": t, "question": question}) for t in tasks]


def build_graph(deps: Deps, checkpointer=None):
    max_drafts = deps.settings.max_revisions + 1

    async def planner_node(state: ResearchState):
        return {"plan": await planner.plan(deps, state["question"]), "round": 0, "drafts": 0}

    def route_after_planner(state: ResearchState):
        return _fan_out(state["plan"], state["question"])

    async def researcher_node(payload: dict):
        finding = await researcher.research(deps, payload["question"], payload["task"])
        return {"findings": [finding]}

    async def analyst_node(state: ResearchState):
        round_no = state.get("round", 0) + 1
        analysis, sources, followups = await analyst.analyze(
            deps, state["question"], state.get("findings", []), round_no
        )
        return {"analysis": analysis, "sources": sources, "followups": followups, "round": round_no}

    def route_after_analyst(state: ResearchState):
        if state.get("followups"):  # cycle back for another parallel research round
            return _fan_out(state["followups"], state["question"])
        if not state.get("sources") or not state["analysis"].insights:
            return "finalize"
        return "approval" if state.get("require_approval") else "writer"

    def approval_node(state: ResearchState):
        a = state["analysis"]
        decision = interrupt(
            {
                "message": "Review the research before the report is written.",
                "insights": [i.model_dump() for i in a.insights],
                "gaps": a.gaps,
                "contradictions": a.contradictions,
                "sources": [s.model_dump() for s in state["sources"]],
            }
        )
        return {
            "approved": bool(decision.get("approved", False)),
            "guidance": decision.get("feedback") or "",
        }

    def route_after_approval(state: ResearchState):
        return "writer" if state["approved"] else "finalize"

    async def writer_node(state: ResearchState):
        crit = state.get("critique")
        draft = await writer.write(
            deps,
            state["question"],
            state["analysis"],
            state["sources"],
            previous_draft=state.get("draft", ""),
            issues=crit.issues if crit else None,
            guidance=state.get("guidance", ""),
        )
        return {"draft": draft, "drafts": state.get("drafts", 0) + 1}

    async def critic_node(state: ResearchState):
        review, check = await critic.critique(
            deps, state["question"], state["draft"], state["analysis"], state["sources"]
        )
        return {"critique": review, "citation_check": check}

    def route_after_critic(state: ResearchState):
        # Bounded loop: stop when approved or when the revision budget is spent.
        if state["critique"].approved or state["drafts"] >= max_drafts:
            return "finalize"
        return "writer"

    def finalize_node(state: ResearchState):
        findings = state.get("findings", [])
        errors = [f"{f.task.query}: {f.error}" for f in findings if f.error]
        analysis = state.get("analysis") or Analysis(insights=[])
        sources = state.get("sources", [])
        dropped = sum(f.dropped_claims for f in findings)
        usage = usage_var.get()
        common = dict(
            question=state["question"],
            sources=sources,
            insights=analysis.insights,
            contradictions=analysis.contradictions,
            gaps=analysis.gaps,
            rounds=state.get("round", 0),
            errors=errors,
            dropped_claims=dropped,
            usage=usage.snapshot() if usage else {},
        )
        warnings = _warnings(findings, sources, dropped)

        if state.get("approved") is False:
            return {
                "report": Report(
                    status="rejected",
                    markdown="Research was rejected by the reviewer.",
                    warnings=warnings,
                    **common,
                )
            }
        if "draft" not in state:
            detail = "; ".join(errors) or "no usable evidence found"
            return {
                "report": Report(
                    status="insufficient_evidence",
                    markdown=f"# Insufficient evidence\n\nCould not research this question: {detail}.",
                    warnings=warnings,
                    **common,
                )
            }
        check = state["citation_check"]
        approved = state["critique"].approved
        if not approved:
            warnings.append("The report did not pass critic review within the revision budget.")
        cited = set(check.cited_ids)
        common["sources"] = [s for s in sources if s.id in cited] or sources
        return {
            "report": Report(
                status="complete",
                markdown=state["draft"].rstrip() + render_sources(sources, check.cited_ids),
                citation_check=check,
                critic_approved=approved,
                drafts=state["drafts"],
                warnings=warnings,
                **common,
            )
        }

    g = StateGraph(ResearchState)
    g.add_node("planner", planner_node)
    g.add_node("researcher", researcher_node)
    g.add_node("analyst", analyst_node)
    g.add_node("approval", approval_node)
    g.add_node("writer", writer_node)
    g.add_node("critic", critic_node)
    g.add_node("finalize", finalize_node)

    g.add_edge(START, "planner")
    g.add_conditional_edges("planner", route_after_planner, ["researcher"])
    g.add_edge("researcher", "analyst")  # fan-in: runs once after all parallel researchers
    g.add_conditional_edges("analyst", route_after_analyst, ["researcher", "approval", "writer", "finalize"])
    g.add_conditional_edges("approval", route_after_approval, ["writer", "finalize"])
    g.add_edge("writer", "critic")
    g.add_conditional_edges("critic", route_after_critic, ["writer", "finalize"])
    g.add_edge("finalize", END)

    # A checkpointer is required for human-in-the-loop (pause/resume by thread_id).
    return g.compile(checkpointer=checkpointer or default_checkpointer())


def _warnings(findings, sources, dropped: int) -> list[str]:
    out: list[str] = []
    failed = sum(1 for f in findings if f.error)
    if failed:
        out.append(f"{failed} of {len(findings)} research tasks failed; coverage may be incomplete.")
    if dropped:
        out.append(
            f"{dropped} claim(s) were discarded because their supporting quote could not be "
            "verified in the source text."
        )
    domains = {urlsplit(s.url).hostname for s in sources}
    if sources and len(domains) < 2:
        out.append("All evidence comes from a single website; treat conclusions with caution.")
    return out
