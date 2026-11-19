import pytest
from fastapi.testclient import TestClient

from mars.api import create_app
from mars.docs import DocumentService, DocumentStore
from mars.storage.embeddings import HashEmbedder
from mars.workflow.service import ResearchService

NOTE = (
    b"Project Zephyr budget review. The Zephyr programme spent 4.2 million dollars in 2025, "
    b"which is 8 percent under the approved budget."
)


@pytest.fixture
def service(settings, tmp_path):
    settings.docs_min_score = 0.0  # the hash embedder is lexical; do not depend on score thresholds
    svc = ResearchService(settings)
    store = DocumentStore(str(tmp_path / "docs.db"), HashEmbedder(256))
    import asyncio

    asyncio.run(store.setup())
    svc.deps.docs = DocumentService(settings, store)
    return svc


@pytest.fixture
def client(settings, service):
    with TestClient(create_app(settings, service)) as c:
        yield c


def test_upload_list_search_delete(client):
    r = client.post("/documents", files=[("files", ("zephyr.txt", NOTE, "text/plain"))])
    assert r.status_code == 200
    item = r.json()[0]
    assert item["status"] == "indexed"
    doc_id = item["document"]["id"]

    assert client.post("/documents", files=[("files", ("zephyr.txt", NOTE, "text/plain"))]).json()[0][
        "status"
    ] == "duplicate"
    assert client.get("/documents").json()[0]["name"] == "zephyr.txt"
    hits = client.get("/documents/search", params={"q": "Zephyr programme budget"}).json()
    assert hits and hits[0]["name"] == "zephyr.txt"
    assert client.get("/health").json()["documents"] is True
    assert client.delete(f"/documents/{doc_id}").status_code == 204
    assert client.delete(f"/documents/{doc_id}").status_code == 404


def test_research_cites_internal_documents(client):
    client.post("/documents", files=[("files", ("zephyr.txt", NOTE, "text/plain"))])
    r = client.post("/research", json={"question": "How did the Zephyr programme budget perform?"})
    assert r.status_code == 200
    sources = r.json()["report"]["sources"]
    assert any(s["url"].startswith("doc://") and "Zephyr" in " ".join(s["quotes"]) for s in sources)


def test_documents_disabled_returns_501(settings):
    with TestClient(create_app(settings, ResearchService(settings))) as c:
        assert c.get("/documents").status_code == 501
        assert c.get("/health").json()["documents"] is False
