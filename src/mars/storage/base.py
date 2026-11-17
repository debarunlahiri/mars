from __future__ import annotations

from typing import Protocol

from ..schemas import Report
from .models import Chunk, ChunkHit, ReportSummary


class StorageError(RuntimeError):
    pass


class Storage(Protocol):
    """Durable report store + vector index over verified source quotes."""

    async def setup(self) -> None: ...

    async def aclose(self) -> None: ...

    async def save_report(self, report_id: str, report: Report) -> None: ...

    async def get_report(self, report_id: str) -> Report | None: ...

    async def list_reports(self, limit: int = 20, offset: int = 0) -> list[ReportSummary]: ...

    async def delete_report(self, report_id: str) -> bool: ...

    async def search(self, query: str, k: int = 5, min_score: float = 0.0) -> list[ChunkHit]: ...


def chunks_from_report(report: Report) -> list[Chunk]:
    """Index only verified quotes (each was matched against its page text during research)."""
    seen: set[tuple[str, str]] = set()
    chunks: list[Chunk] = []
    for s in report.sources:
        for quote in s.quotes:
            key = (s.url, quote)
            if quote.strip() and key not in seen:
                seen.add(key)
                chunks.append(Chunk(text=quote, url=s.url, title=s.title, published=s.published))
    return chunks
