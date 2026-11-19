"""Graph state."""

from __future__ import annotations

import operator
from typing import Annotated, TypedDict

from ..schemas import Analysis, CitationCheck, Critique, Finding, Report, ResearchTask, Source

# Only our own schema types may be deserialized from checkpoints (safe under strict msgpack).
ALLOWED_TYPES = [
    ("mars.schemas", name)
    for name in (
        "Finding",
        "ResearchTask",
        "Analysis",
        "Source",
        "Critique",
        "CitationCheck",
        "Report",
        "KeyPoint",
        "SearchResult",
        "Insight",
    )
]


class ResearchState(TypedDict, total=False):
    question: str
    require_approval: bool
    scope: dict  # {"document_ids": [...], "web": bool}: files attached to the question
    plan: list[ResearchTask]
    # Reducer: parallel researchers (and later rounds) all append to the same list.
    findings: Annotated[list[Finding], operator.add]
    followups: list[ResearchTask]
    round: int
    analysis: Analysis
    sources: list[Source]
    approved: bool  # set only if a human decided
    guidance: str  # human feedback for the writer
    draft: str
    drafts: int
    critique: Critique
    citation_check: CitationCheck
    report: Report
