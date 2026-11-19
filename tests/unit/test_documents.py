import io

import pytest

from mars.docs import DocumentService, DocumentStore, ExtractionError, is_doc_url, resolve_device
from mars.docs.chunk import Segment, chunk_segments
from mars.docs.extract import extract
from mars.storage.embeddings import HashEmbedder


def test_chunking_is_bounded_overlapping_and_keeps_labels():
    para = "Revenue grew strongly in the third quarter. " * 6
    text = "\n\n".join(f"Paragraph {i}. {para}" for i in range(8))
    chunks = chunk_segments([Segment(text, "p1"), Segment("short slide", "slide 2")], size=600, overlap=80)
    assert all(len(c.text) <= 700 for c in chunks)
    assert [c.pos for c in chunks] == list(range(len(chunks)))
    assert chunks[-1].label == "slide 2" and chunks[-1].text == "short slide"
    assert len(chunks) > 3


def test_device_resolution_always_returns_something_usable():
    assert resolve_device("auto") in {"cuda", "mps", "cpu"}
    assert resolve_device("cpu") == "cpu"
    assert resolve_device("cuda") in {"cuda", "mps", "cpu"}  # unavailable -> falls back, never raises


async def test_text_and_unsupported_and_legacy_files():
    out = await extract("notes.md", b"# Title\n\nHello world, this is a note.")
    assert out.kind == "text" and "Hello world" in out.segments[0].text
    with pytest.raises(ExtractionError, match="unsupported"):
        await extract("movie.mp4", b"\x00\x01")
    with pytest.raises(ExtractionError, match="legacy"):
        await extract("old.doc", b"\x00")
    with pytest.raises(ExtractionError, match="no readable text"):
        await extract("empty.txt", b"   \n  ")


async def test_image_without_vision_or_ocr_fails_clearly():
    with pytest.raises(ExtractionError):
        await extract("scan.png", b"not really a png")


async def test_image_uses_the_vision_model():
    async def vision(data: bytes, mime: str) -> str:
        assert mime == "image/png"
        return "Bar chart: revenue 2024 = 12M"

    out = await extract("chart.png", b"\x89PNG....", vision)
    assert out.kind == "image" and "revenue 2024" in out.segments[0].text


async def test_xlsx_values_keep_their_column_headers():
    openpyxl = pytest.importorskip("openpyxl")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Sales"
    ws.append(["Region", "Revenue"])
    ws.append(["EMEA", 1200])
    buf = io.BytesIO()
    wb.save(buf)
    out = await extract("sales.xlsx", buf.getvalue())
    assert out.segments[0].label == "sheet Sales"
    assert "Revenue: 1200" in out.segments[0].text


async def test_docx_and_pptx_roundtrip():
    docx = pytest.importorskip("docx")
    pptx = pytest.importorskip("pptx")
    d = docx.Document()
    d.add_heading("Churn report", 1)
    d.add_paragraph("Churn fell to 3.1 percent in Q3.")
    buf = io.BytesIO()
    d.save(buf)
    out = await extract("churn.docx", buf.getvalue())
    assert "Churn fell to 3.1 percent" in out.segments[0].text

    prs = pptx.Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = "Roadmap"
    slide.placeholders[1].text = "Launch the mobile app in Q4"
    buf = io.BytesIO()
    prs.save(buf)
    out = await extract("deck.pptx", buf.getvalue())
    assert out.segments[0].label == "slide 1" and "mobile app" in out.segments[0].text


@pytest.fixture
async def docs(settings, tmp_path):
    store = DocumentStore(str(tmp_path / "docs.db"), HashEmbedder(256))
    await store.setup()
    svc = DocumentService(settings, store)
    yield svc
    await svc.aclose()


async def test_ingest_search_dedupe_delete(docs):
    text = b"Hybrid retrieval combines BM25 with dense vectors.\n\nThe cafeteria opens at nine."
    r = await docs.ingest("rag.txt", text)
    assert r.status == "indexed" and r.document.chunks >= 1
    assert (await docs.ingest("copy.txt", text)).status == "duplicate"
    assert (await docs.ingest("bad.xyz", b"data")).status == "failed"
    assert (await docs.ingest("empty.txt", b"")).status == "failed"

    ev = await docs.evidence("hybrid retrieval BM25 dense vectors")
    assert ev and is_doc_url(ev[0].url) and "BM25" in ev[0].evidence
    assert "internal document" in ev[0].title

    assert await docs.delete(r.document.id)
    assert await docs.evidence("hybrid retrieval BM25") == []


async def test_upload_size_limit(docs):
    docs.settings.max_upload_mb = 0
    assert (await docs.ingest("a.txt", b"x")).status == "failed"
