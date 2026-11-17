"""Analyst: dedupe sources into one numbered registry, cross-check evidence, find gaps."""

from __future__ import annotations

from ..prompts import ANALYST_SYSTEM, analyst_user, stamped
from ..schemas import Analysis, Finding, Insight, ResearchTask, Source
from ..tools.search import canonical_url
from ..workflow.deps import Deps


def build_evidence(findings: list[Finding]) -> tuple[list[Source], list[tuple[str, list[int]]]]:
    """Return the global source registry (stable ids) and evidence points tagged with those ids.

    Deterministic code (not the LLM) owns source ids, so a citation id can always be traced
    back to a real retrieved URL.
    """
    by_url: dict[str, Source] = {}
    points: list[tuple[str, list[int]]] = []
    for f in sorted((f for f in findings if not f.error), key=lambda f: f.task.id):
        meta = {canonical_url(r.url): r for r in f.sources}
        for kp in f.key_points:
            ids: list[int] = []
            for url in kp.source_urls:
                key = canonical_url(url)
                if key not in by_url:
                    r = meta.get(key)
                    by_url[key] = Source(
                        id=len(by_url) + 1,
                        title=r.title if r else url,
                        url=key,
                        snippet=(r.snippet[:300] if r else ""),
                        published=r.published if r else None,
                    )
                src = by_url[key]
                if kp.quote and kp.quote not in src.quotes and len(src.quotes) < 6:
                    src.quotes.append(kp.quote)
                ids.append(src.id)
            points.append((kp.text, sorted(set(ids))))
    return list(by_url.values()), points


async def analyze(
    deps: Deps, question: str, findings: list[Finding], round_no: int
) -> tuple[Analysis, list[Source], list[ResearchTask]]:
    sources, points = build_evidence(findings)
    if not points:
        return Analysis(insights=[], gaps=["No usable evidence was retrieved."]), [], []

    out = await deps.strong.structured(
        Analysis, stamped(ANALYST_SYSTEM), analyst_user(question, points, sources)
    )

    # Hallucination control: drop invented source ids; an insight needs real support.
    valid = {s.id for s in sources}
    insights = []
    for ins in out.insights:
        ids = sorted(set(ins.source_ids) & valid)
        if ids and ins.text.strip():
            insights.append(Insight(text=ins.text.strip(), source_ids=ids))
    analysis = out.model_copy(update={"insights": insights})

    # Cycle: if there are gaps and budget left, request another (parallel) research round.
    followups: list[ResearchTask] = []
    if round_no < deps.settings.max_rounds:
        done = {f.task.query.casefold() for f in findings}
        followups = [
            ResearchTask(id=f"r{round_no + 1}-{i}", query=q.strip(), rationale="follow-up on gap")
            for i, q in enumerate(out.followup_queries[:2], start=1)
            if q.strip() and q.strip().casefold() not in done
        ]
    return analysis, sources, followups
