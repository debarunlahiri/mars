"""Turn an uploaded file into text segments.

Supported: plain text / markdown / CSV / JSON / HTML, PDF, Word (.docx), PowerPoint (.pptx),
Excel (.xlsx) and images (PNG, JPEG, WebP, GIF, BMP, TIFF). Images are read by the vision LLM
(when the provider has one) and/or an optional OCR engine.
"""

from __future__ import annotations

import asyncio
import io
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import PurePath

from ..core.logging import get_logger
from .chunk import Segment

log = get_logger("extract")

# async (image bytes, mime type) -> transcription / description
Vision = Callable[[bytes, str], Awaitable[str]]

TEXT_EXT = {
    ".txt", ".md", ".markdown", ".rst", ".log", ".csv", ".tsv", ".json", ".jsonl",
    ".yaml", ".yml", ".xml", ".ini", ".toml", ".py", ".js", ".ts", ".java", ".c", ".cpp", ".go", ".rs", ".sql",
}  # fmt: skip
HTML_EXT = {".html", ".htm"}
IMAGE_EXT = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp",
    ".gif": "image/gif", ".bmp": "image/bmp", ".tif": "image/tiff", ".tiff": "image/tiff",
}  # fmt: skip
SUPPORTED = sorted(TEXT_EXT | HTML_EXT | set(IMAGE_EXT) | {".pdf", ".docx", ".pptx", ".xlsx"})

MAX_EMBEDDED_IMAGES = 8  # per document; keeps vision cost bounded
MIN_IMAGE_BYTES = 8_000  # skips icons, bullets and logos
MAX_SHEET_ROWS = 5000


class ExtractionError(ValueError):
    """The file could not be read (unsupported type, corrupt file, missing optional library)."""


@dataclass
class Extracted:
    kind: str
    segments: list[Segment] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)  # non-fatal problems the uploader should see

    @property
    def chars(self) -> int:
        return sum(len(s.text) for s in self.segments)


def _need(package: str, extra: str = "documents"):
    raise ExtractionError(f"reading this file needs the '{package}' package: pip install 'mars[{extra}]'")


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-16"):
        try:
            return data.decode(enc)
        except UnicodeError:
            continue
    return data.decode("latin-1", errors="replace")


def _text(data: bytes) -> Extracted:
    return Extracted("text", [Segment(_decode(data))])


def _html(data: bytes) -> Extracted:
    raw = _decode(data)
    try:
        import trafilatura

        text = trafilatura.extract(raw, include_tables=True) or ""
    except Exception:  # noqa: BLE001
        text = ""
    if not text:
        text = re.sub(r"<(script|style)\b.*?</\1>", " ", raw, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
    return Extracted("html", [Segment(text)])


# ------------------------------------------------------------------ images


async def _ocr(data: bytes) -> str:
    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError:
        return ""

    def run() -> str:
        result, _ = RapidOCR()(data)
        return "\n".join(r[1] for r in (result or []))

    try:
        return await asyncio.to_thread(run)
    except Exception as exc:  # noqa: BLE001
        log.warning("OCR failed: %s: %s", type(exc).__name__, str(exc)[:120])
        return ""


async def read_image(data: bytes, mime: str, vision: Vision | None) -> str:
    """Vision model first (understands charts and layout); OCR as the offline fallback."""
    if vision is not None:
        try:
            text = (await vision(data, mime)).strip()
            if text:
                return text
        except Exception as exc:  # noqa: BLE001
            log.warning("vision failed: %s: %s", type(exc).__name__, str(exc)[:150])
    return (await _ocr(data)).strip()


async def _image(data: bytes, mime: str, vision: Vision | None) -> Extracted:
    text = await read_image(data, mime, vision)
    if not text:
        raise ExtractionError(
            "no text could be read from this image: it needs a vision-capable LLM provider "
            "(not the offline mock) or the OCR extra: pip install 'mars[ocr]'"
        )
    return Extracted("image", [Segment(text, "image")])


# ------------------------------------------------------------------ office / pdf


async def _pdf(data: bytes, vision: Vision | None) -> Extracted:
    try:
        from pypdf import PdfReader
    except ImportError:
        _need("pypdf")
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise ExtractionError("the PDF is password protected")
        pages = reader.pages
    except ExtractionError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"not a readable PDF ({type(exc).__name__})") from exc

    out = Extracted("pdf")
    scanned = 0
    for n, page in enumerate(pages, 1):
        text = (page.extract_text() or "").strip()
        if not text:  # scanned page: its content is an image
            scanned += 1
            if scanned <= MAX_EMBEDDED_IMAGES:
                for img in list(page.images)[:1]:
                    text = await read_image(img.data, "image/png", vision)
        if text:
            out.segments.append(Segment(text, f"p{n}"))
    if scanned:
        out.notes.append(
            f"{scanned} page(s) had no text layer (scans); "
            + ("read via vision/OCR" if vision else "enable a vision LLM or OCR to read them")
            + (f", at most {MAX_EMBEDDED_IMAGES}" if scanned > MAX_EMBEDDED_IMAGES else "")
        )
    return out


async def _docx(data: bytes, vision: Vision | None) -> Extracted:
    try:
        from docx import Document
        from docx.table import Table
        from docx.text.paragraph import Paragraph
    except ImportError:
        _need("python-docx")
    try:
        doc = Document(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"not a readable .docx ({type(exc).__name__})") from exc

    blocks: list[str] = []
    for child in doc.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            para = Paragraph(child, doc)
            text = para.text.strip()
            if text and (para.style is not None and (para.style.name or "").startswith("Heading")):
                text = "## " + text
            if text:
                blocks.append(text)
        elif tag == "tbl":
            rows = [" | ".join(c.text.strip() for c in r.cells) for r in Table(child, doc).rows]
            blocks.append("\n".join(r for r in rows if r.strip(" |")))
    out = Extracted("docx", [Segment("\n\n".join(b for b in blocks if b))])

    if vision is not None:
        images = [
            p.blob
            for p in doc.part.package.iter_parts()
            if str(p.content_type).startswith("image/") and len(p.blob) >= MIN_IMAGE_BYTES
        ][:MAX_EMBEDDED_IMAGES]
        for i, blob in enumerate(images, 1):
            if text := await read_image(blob, "image/png", vision):
                out.segments.append(Segment(text, f"embedded image {i}"))
    return out


def _shape_texts(shapes) -> list[str]:
    texts: list[str] = []
    for sh in shapes:
        if getattr(sh, "shapes", None) is not None:  # group
            texts += _shape_texts(sh.shapes)
        if getattr(sh, "has_text_frame", False) and sh.text_frame.text.strip():
            texts.append(sh.text_frame.text.strip())
        if getattr(sh, "has_table", False) and sh.has_table:
            for row in sh.table.rows:
                line = " | ".join(c.text.strip() for c in row.cells)
                if line.strip(" |"):
                    texts.append(line)
    return texts


def _pictures(shapes) -> list:
    pics = []
    for sh in shapes:
        if getattr(sh, "shapes", None) is not None:
            pics += _pictures(sh.shapes)
        elif sh.shape_type == 13:  # MSO_SHAPE_TYPE.PICTURE
            pics.append(sh)
    return pics


async def _pptx(data: bytes, vision: Vision | None) -> Extracted:
    try:
        from pptx import Presentation
    except ImportError:
        _need("python-pptx")
    try:
        prs = Presentation(io.BytesIO(data))
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"not a readable .pptx ({type(exc).__name__})") from exc

    out = Extracted("pptx")
    budget = MAX_EMBEDDED_IMAGES
    for n, slide in enumerate(prs.slides, 1):
        parts = _shape_texts(slide.shapes)
        if slide.has_notes_slide and slide.notes_slide.notes_text_frame is not None:
            if notes := slide.notes_slide.notes_text_frame.text.strip():
                parts.append("Speaker notes: " + notes)
        if vision is not None and budget > 0:
            for pic in _pictures(slide.shapes):
                if budget <= 0 or len(pic.image.blob) < MIN_IMAGE_BYTES:
                    continue
                budget -= 1
                if text := await read_image(pic.image.blob, pic.image.content_type, vision):
                    parts.append("Image on slide: " + text)
        if parts:
            out.segments.append(Segment("\n\n".join(parts), f"slide {n}"))
    return out


def _xlsx(data: bytes) -> Extracted:
    try:
        from openpyxl import load_workbook
    except ImportError:
        _need("openpyxl")
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:  # noqa: BLE001
        raise ExtractionError(f"not a readable .xlsx ({type(exc).__name__})") from exc

    out = Extracted("xlsx")
    for ws in wb.worksheets:
        lines: list[str] = []
        header: list[str] | None = None
        for i, row in enumerate(ws.iter_rows(values_only=True)):
            if i >= MAX_SHEET_ROWS:
                out.notes.append(f"sheet '{ws.title}' truncated at {MAX_SHEET_ROWS} rows")
                break
            cells = ["" if v is None else str(v).strip() for v in row]
            if not any(cells):
                continue
            if header is None:
                header = cells
                lines.append(" | ".join(cells))
            else:  # "column: value" keeps numbers attached to their header for retrieval
                lines.append(" | ".join(f"{h}: {c}" if h and c else c for h, c in zip(header, cells, strict=False)))
        if lines:
            out.segments.append(Segment("\n".join(lines), f"sheet {ws.title}"))
    wb.close()
    return out


# ------------------------------------------------------------------ entry point


async def extract(name: str, data: bytes, vision: Vision | None = None) -> Extracted:
    ext = PurePath(name).suffix.lower()
    if ext in TEXT_EXT:
        out = _text(data)
    elif ext in HTML_EXT:
        out = _html(data)
    elif ext in IMAGE_EXT:
        out = await _image(data, IMAGE_EXT[ext], vision)
    elif ext == ".pdf":
        out = await _pdf(data, vision)
    elif ext == ".docx":
        out = await _docx(data, vision)
    elif ext == ".pptx":
        out = await _pptx(data, vision)
    elif ext == ".xlsx":
        out = await asyncio.to_thread(_xlsx, data)
    elif ext in {".doc", ".ppt", ".xls"}:
        raise ExtractionError(f"legacy {ext} files are not supported; save as {ext}x and upload again")
    else:
        raise ExtractionError(f"unsupported file type {ext or '(none)'}; supported: {', '.join(SUPPORTED)}")
    out.segments = [s for s in out.segments if s.text.strip()]
    if not out.segments:
        raise ExtractionError("no readable text found in the file")
    return out
