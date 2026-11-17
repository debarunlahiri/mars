import asyncio

from conftest import collect
from mars.evaluation import evaluate
from mars.schemas import Critique, Report
from mars.workflow.deps import build_deps
from mars.workflow.graph import build_graph
from mars.workflow.service import ResearchService

Q = "How does retrieval augmented generation work?"


async def test_end_to_end_report_is_cited(service):
    events = await collect(service.start(Q))
    nodes = [e["node"] for e in events if e["event"] == "step"]

    assert nodes[0] == "planner"
    assert nodes.count("researcher") == 3  # planner fanned out three parallel tasks
    assert nodes[-1] == "finalize"

    report = events[-1]["report"]
    assert report["status"] == "complete"
    assert report["citation_check"]["cited_ids"]
    assert not report["citation_check"]["invalid_ids"]
    assert "## Sources" in report["markdown"]
    assert report["critic_approved"] is True
    assert report["usage"] is not None


async def test_usage_is_tracked_per_run(settings):
    from mars.core.usage import track

    deps = build_deps(settings)
    orig = deps.strong.text

    async def counting(system, user):
        track(llm_calls=1, input_tokens=10, output_tokens=5)
        return await orig(system, user)

    deps.strong.text = counting  # type: ignore[method-assign]
    svc = ResearchService(settings, deps=deps)
    events = await collect(svc.start(Q))
    assert events[-1]["report"]["usage"]["llm_calls"] == 1
    again = await collect(svc.start(Q))
    assert again[-1]["report"]["usage"]["llm_calls"] == 1  # not accumulated across runs


async def test_human_approval_pause_and_resume(service):
    events = await collect(service.start(Q, require_approval=True))
    assert events[-1]["event"] == "awaiting_approval"
    thread_id = events[-1]["thread_id"]
    assert events[-1]["preview"]["insights"]
    assert await service.is_waiting(thread_id)

    resumed = await collect(service.resume(thread_id, approved=True, feedback="be brief"))
    assert resumed[-1]["event"] == "report"
    assert resumed[-1]["report"]["status"] == "complete"
    assert not await service.is_waiting(thread_id)


async def test_human_rejection_skips_writer(service):
    events = await collect(service.start(Q, True))
    resumed = await collect(service.resume(events[-1]["thread_id"], approved=False))
    nodes = [e["node"] for e in resumed if e["event"] == "step"]
    assert "writer" not in nodes
    assert resumed[-1]["report"]["status"] == "rejected"


async def test_critic_loop_is_bounded(settings):
    deps = build_deps(settings)
    calls = 0
    original = deps.strong.structured

    async def always_reject(schema, system, user):
        nonlocal calls
        if schema is Critique:
            calls += 1
            return Critique(approved=False, issues=["not good enough"])
        return await original(schema, system, user)

    deps.strong.structured = always_reject  # type: ignore[method-assign]
    out = await build_graph(deps).ainvoke(
        {"question": "bounded loop test", "findings": []}, {"configurable": {"thread_id": "t"}}
    )
    assert calls == settings.max_revisions + 1
    assert out["report"].drafts == settings.max_revisions + 1
    assert out["report"].critic_approved is False
    assert any("critic review" in w for w in out["report"].warnings)


async def test_no_evidence_returns_insufficient_evidence(settings):
    deps = build_deps(settings)

    async def empty(query, max_results=5):
        return []

    deps.search.search = empty  # type: ignore[method-assign]
    out = await build_graph(deps).ainvoke(
        {"question": "nothing findable", "findings": []}, {"configurable": {"thread_id": "t"}}
    )
    assert out["report"].status == "insufficient_evidence"
    assert out["report"].errors


async def test_partial_failure_still_produces_report_with_warning(settings):
    deps = build_deps(settings)
    original = deps.search.search

    async def flaky(query, max_results=5):
        if "risks" in query:
            raise RuntimeError("provider outage")
        return await original(query, max_results)

    deps.search.search = flaky  # type: ignore[method-assign]
    out = await build_graph(deps).ainvoke(
        {"question": "partial failure", "findings": []}, {"configurable": {"thread_id": "t"}}
    )
    report = out["report"]
    assert report.status == "complete" and len(report.errors) == 1
    assert any("1 of 3 research tasks failed" in w for w in report.warnings)


async def test_run_timeout_yields_error_event(settings):
    slow = settings.model_copy(update={"run_timeout": 0.2})
    deps = build_deps(slow)

    async def hang(query, max_results=5):
        await asyncio.sleep(5)

    deps.search.search = hang  # type: ignore[method-assign]
    svc = ResearchService(slow, deps=deps)
    events = await collect(svc.start(Q))
    assert events[-1]["event"] == "error" and events[-1]["code"] == "run_timeout"
    assert svc.active == 0  # slot released


async def test_unexpected_errors_do_not_leak_internals(settings):
    deps = build_deps(settings)

    async def crash(schema, system, user):
        raise RuntimeError("secret-internal-detail")

    deps.fast.structured = crash  # type: ignore[method-assign]
    events = await collect(ResearchService(settings, deps=deps).start(Q))
    err = events[-1]
    assert err["event"] == "error" and err["code"] == "internal_error"
    assert "secret-internal-detail" not in err["detail"] and "error_id=" in err["detail"]


async def test_eval_passes_on_good_report(service, settings):
    events = await collect(service.start(Q))
    result = await evaluate(Report.model_validate(events[-1]["report"]), build_deps(settings))
    assert result.passed and result.has_citations and result.citations_valid
    assert result.lexical_support > 0.5
