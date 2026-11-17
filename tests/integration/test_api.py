import json

import pytest
from fastapi.testclient import TestClient

from mars.api import create_app
from mars.workflow.service import ResearchService

Q = {"question": "How does retrieval augmented generation work?"}


@pytest.fixture
def client(settings, service):
    with TestClient(create_app(settings, service)) as c:
        yield c


def test_blocking_endpoint(client):
    assert client.get("/health").json()["status"] == "ok"
    r = client.post("/research", json=Q)
    assert r.status_code == 200 and "x-request-id" in r.headers
    body = r.json()
    assert body["status"] == "complete"
    assert body["report"]["citation_check"]["cited_ids"]


def test_validation(client):
    assert client.post("/research", json={"question": "hi"}).status_code == 422
    assert client.post("/research", json={"question": "x" * 1001}).status_code == 422
    assert client.post("/research", json={"question": "   \x00\x00   "}).status_code == 422


def test_sse_stream(client):
    with client.stream("POST", "/research/stream", json=Q) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        text = "".join(r.iter_text())
    events = [json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")]
    assert events[0]["event"] == "started" and events[-1]["event"] == "report"
    assert any(e.get("node") == "researcher" for e in events)


def test_approval_flow(client):
    first = client.post("/research", json={**Q, "require_approval": True}).json()
    assert first["status"] == "awaiting_approval" and first["preview"]["insights"]
    url = f"/research/{first['thread_id']}/approve"
    assert client.post(url, json={"approved": True, "feedback": "short"}).json()["status"] == "complete"
    assert client.post(url, json={"approved": True}).status_code == 404  # already finished


def test_unknown_thread_is_404(client):
    r = client.post("/research/nope/approve", json={"approved": True})
    assert r.status_code == 404 and r.json()["code"] == "error"


def test_api_key_auth(settings, service):
    s = settings.model_copy(update={"api_keys": "secret-one, secret-two"})
    with TestClient(create_app(s, service)) as c:
        assert c.get("/health").status_code == 200  # health stays open
        assert c.post("/research", json=Q).status_code == 401
        assert c.post("/research", json=Q, headers={"X-API-Key": "wrong"}).status_code == 401
        assert c.post("/research", json=Q, headers={"X-API-Key": "secret-two"}).status_code == 200
        assert c.post("/research", json=Q, headers={"Authorization": "Bearer secret-one"}).status_code == 200


def test_rate_limit(settings, service):
    s = settings.model_copy(update={"rate_limit_per_min": 2})
    with TestClient(create_app(s, service)) as c:
        assert c.post("/research", json=Q).status_code == 200
        assert c.post("/research", json=Q).status_code == 200
        r = c.post("/research", json=Q)
        assert r.status_code == 429 and int(r.headers["retry-after"]) >= 1


def test_load_shedding_when_busy(settings, service):
    s = settings.model_copy(update={"max_concurrent_runs": 1})
    service.active = 1  # one run already in flight
    with TestClient(create_app(s, service)) as c:
        r = c.post("/research", json=Q)
        assert r.status_code == 503 and r.headers["retry-after"]


def test_pipeline_errors_map_to_http_status(settings):
    svc = ResearchService(settings)

    async def failing(*a, **k):
        yield {"event": "started", "thread_id": "t"}
        yield {"event": "error", "thread_id": "t", "code": "run_timeout", "status": 504, "detail": "slow"}

    svc.start = failing  # type: ignore[method-assign]
    with TestClient(create_app(settings, svc)) as c:
        r = c.post("/research", json=Q)
        assert r.status_code == 504 and r.json() == {"code": "run_timeout", "detail": "slow"}


def test_paused_run_survives_restart_with_sqlite(settings, tmp_path):
    s = settings.model_copy(update={"checkpoint_db": str(tmp_path / "mars.db")})
    with TestClient(create_app(s)) as c1:
        first = c1.post("/research", json={**Q, "require_approval": True}).json()
        assert first["status"] == "awaiting_approval"
    # New process-equivalent: fresh app, same database file.
    with TestClient(create_app(s)) as c2:
        done = c2.post(f"/research/{first['thread_id']}/approve", json={"approved": True}).json()
        assert done["status"] == "complete"
