from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class Chunk(BaseModel):
    """One verified quote from a source, indexed for semantic recall."""

    text: str
    url: str
    title: str
    published: str | None = None


class ChunkHit(BaseModel):
    text: str
    url: str
    title: str
    published: str | None = None
    report_id: str
    score: float  # cosine similarity, higher = closer
    indexed_at: datetime


class ReportSummary(BaseModel):
    id: str
    question: str
    status: str
    created_at: datetime
    sources: int
    warnings: int
