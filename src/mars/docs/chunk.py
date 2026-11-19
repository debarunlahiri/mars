"""Split extracted text into overlapping, paragraph-aware passages for embedding."""

from __future__ import annotations

import re
from dataclasses import dataclass

_PARA = re.compile(r"\n\s*\n")


@dataclass
class Segment:
    """A natural unit of a document: a PDF page, a slide, a sheet, or the whole text."""

    text: str
    label: str = ""  # e.g. "p3", "slide 2", "sheet Sales"


@dataclass
class DocChunk:
    text: str
    label: str
    pos: int  # running index within the document


def _pieces(text: str, size: int) -> list[str]:
    """Paragraphs, with any paragraph longer than ``size`` cut at whitespace."""
    out: list[str] = []
    for para in _PARA.split(text):
        para = para.strip()
        while len(para) > size:
            cut = para.rfind(" ", 0, size)
            cut = cut if cut > size // 2 else size
            out.append(para[:cut].strip())
            para = para[cut:].strip()
        if para:
            out.append(para)
    return out


def chunk_segments(segments: list[Segment], size: int = 1200, overlap: int = 150) -> list[DocChunk]:
    size = max(size, 200)
    overlap = min(max(overlap, 0), size // 3)
    chunks: list[DocChunk] = []
    for seg in segments:
        buf = ""
        for piece in _pieces(seg.text, size):
            if buf and len(buf) + len(piece) + 2 > size:
                chunks.append(DocChunk(buf, seg.label, len(chunks)))
                tail = buf[-overlap:].split(" ", 1)[-1] if overlap else ""  # start on a word boundary
                buf = tail
            buf = f"{buf}\n\n{piece}".strip() if buf else piece
        if buf.strip():
            chunks.append(DocChunk(buf, seg.label, len(chunks)))
    return chunks
