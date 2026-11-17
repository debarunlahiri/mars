import pytest
from fastapi.testclient import TestClient

from conftest import collect
from mars.agents.researcher import research
from mars.api import create_app
from mars.schemas import KeyPoint, Report, ResearchTask, Source, TaskFindings
from mars.storage import StorageError
from mars.storage.embeddings import HashEmbedder
from mars.storage.postgres import PostgresStorage
from mars.storage.sqlite import SqliteStorage
from mars.workflow.deps import build_deps
from mars.workflow.runtime import open_runtime

Q = {"question": "How does retrieval augmented generation work?"}


def make_report(
    question="How does hybrid retrieval work?",
    quote="Hybrid retrieval yields 42 percent higher recall than dense retrieval alone",
) -> Report:
    return Report(
        question=question,
        status="complete",
        markdown="## Summary\n\nHybrid retrieval helps [1].",
        sources=[
            Source(id=1, title="Hybrid paper", url="https://a.com/hybrid", quotes=[quote]),
            Source(id=2, title="Weather", url="https://b.com/w", quotes=["Lisbon is sunny and warm in July"]),
        ],
        warnings=["w1"],
    )


@pytest.fixture(params=["sqlite", "postgres"])
async def store(request, tmp_path):
    emb = HashEmbedder(64)
    if request.param == "sqlite":
        s = SqliteStorage(str(tmp_path / "s.db"), emb)
    else:
        s = PostgresStorage(request.getfixturevalue("pg_url"), emb)
    await s.setup()
    yield s
    await s.aclose()


async def test_roundtrip_list_and_summary(store):
    await store.save_report("r1", make_report("first question here"))
    await store.save_report("r2", make_report("second question here"))
    got = await store.get_report("r1")
    assert got and got.question == "first question here" and got.sources[0].quotes
    listed = await store.list_reports()
    assert [r.id for r in listed] == ["r2", "r1"]  # newest first
    assert listed[0].sources == 2 and listed[0].warnings == 1
    assert await store.get_report("missing") is None
    assert [r.id for r in await store.list_reports(limit=1, offset=1)] == ["r1"]


async def test_semantic_search_ranks_relevant_quote_first(store):
    await store.save_report("r1", make_report())
    hits = await store.search("hybrid retrieval recall", k=2, min_score=-1.0)
    assert hits[0].url == "https://a.com/hybrid" and hits[0].report_id == "r1"
    assert hits[0].score > hits[1].score
    assert await store.search("hybrid retrieval recall", k=2, min_score=0.99) == []


async def test_resave_replaces_and_delete_cascades(store):
    await store.save_report("r1", make_report())
    await store.save_report("r1", make_report())  # same id: replaced, chunks not duplicated
    assert len(await store.search("lisbon sunny", k=10, min_score=-1.0)) == 2
    assert await store.delete_report("r1") is True
    assert await store.search("lisbon sunny", k=10, min_score=-1.0) == []
    assert await store.delete_report("r1") is False


async def test_embedding_mismatch_is_refused(store, tmp_path):
    other = HashEmbedder(32)
    if isinstance(store, SqliteStorage):
        again = SqliteStorage(store.path, other)
    else:
        again = PostgresStorage(store.url, other)
    with pytest.raises(StorageError, match="embeddings"):
        await again.setup()


# --------------------------------------------------------------- service / memory / API
async def test_service_persists_report_and_failure_does_not_break_run(settings, tmp_path):
    s = settings.model_copy(update={"storage_db": str(tmp_path / "m.db")})
    rt = await open_runtime(s)
    try:
        events = await collect(rt.service.start(Q["question"]))
        assert events[-1]["event"] == "report" and events[-1]["stored"] is True
        stored = await rt.service.deps.storage.get_report(events[-1]["thread_id"])
        assert stored and stored.status == "complete"

        async def broken(*a, **k):
            raise RuntimeError("db down")

        rt.service.deps.storage.save_report = broken
        again = await collect(rt.service.start(Q["question"]))
        assert again[-1]["event"] == "report" and again[-1]["stored"] is False
    finally:
        await rt.aclose()


async def test_researcher_reuses_verified_quotes_from_memory(settings, tmp_path):
    s = settings.model_copy(update={"use_memory": True, "memory_min_score": 0.1})
    deps = build_deps(s)
    deps.storage = SqliteStorage(str(tmp_path / "m.db"), HashEmbedder(256))
    await deps.storage.setup()
    await deps.storage.save_report("old", make_report())
    seen = {}

    async def fake(schema, system, user):
        seen["user"] = user
        return TaskFindings(
            summary="s",
            key_points=[
                KeyPoint(
                    text="Hybrid beats dense",
                    source_urls=["https://a.com/hybrid"],
                    quote="Hybrid retrieval yields 42 percent higher recall than dense retrieval alone",
                )
            ],
        )

    deps.fast.structured = fake
    f = await research(deps, "q", ResearchTask(id="t1", query="hybrid retrieval recall"))
    assert "earlier research, indexed" in seen["user"]
    assert [kp.text for kp in f.key_points] == ["Hybrid beats dense"]  # verified against the stored quote
    await deps.storage.aclose()


async def test_memory_failure_is_ignored(settings):
    s = settings.model_copy(update={"use_memory": True})
    deps = build_deps(s)

    class Broken:
        async def search(self, *a, **k):
            raise RuntimeError("vector db down")

    deps.storage = Broken()
    f = await research(deps, "q", ResearchTask(id="t1", query="q"))
    assert f.error is None and f.key_points


def test_reports_api_end_to_end(settings, tmp_path):
    s = settings.model_copy(update={"storage_db": str(tmp_path / "api.db")})
    with TestClient(create_app(s)) as c:
        assert c.get("/health").json()["storage"] == "sqlite"
        rid = c.post("/research", json=Q).json()["thread_id"]
        assert [r["id"] for r in c.get("/reports").json()] == [rid]
        assert c.get(f"/reports/{rid}").json()["status"] == "complete"
        hits = c.get("/memory/search", params={"q": "placeholder evidence", "k": 3}).json()
        assert hits and hits[0]["report_id"] == rid
        assert c.delete(f"/reports/{rid}").status_code == 204
        assert c.get(f"/reports/{rid}").status_code == 404
        assert c.get("/memory/search", params={"q": "ab"}).status_code == 422


def test_reports_api_disabled_without_storage(settings, service):
    with TestClient(create_app(settings, service)) as c:
        r = c.get("/reports")
        assert r.status_code == 501 and r.json()["code"] == "storage_disabled"


async def test_postgres_runtime_end_to_end_with_resume_after_restart(settings, pg_url):
    """Reports, vectors AND paused-run checkpoints all in one real PostgreSQL."""
    s = settings.model_copy(update={"database_url": pg_url})
    rt1 = await open_runtime(s)
    events = await collect(rt1.service.start(Q["question"], require_approval=True))
    thread_id = events[-1]["thread_id"]
    assert events[-1]["event"] == "awaiting_approval"
    await rt1.aclose()  # "restart"

    rt2 = await open_runtime(s)
    try:
        assert await rt2.service.is_waiting(thread_id)
        done = await collect(rt2.service.resume(thread_id, approved=True))
        assert done[-1]["event"] == "report" and done[-1]["stored"] is True
        assert (await rt2.service.deps.storage.get_report(thread_id)).status == "complete"
        hits = await rt2.service.deps.storage.search("placeholder evidence", k=3)
        assert hits and hits[0].report_id == thread_id
    finally:
        await rt2.aclose()
