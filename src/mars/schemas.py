"""Typed data passed between agents. Everything in graph state is one of these models."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------------------------------------------------------- planning


class PlannedTask(BaseModel):
    """LLM output for one sub-task."""

    query: str = Field(description="A focused, self-contained web search query")
    rationale: str = Field(default="", description="Why this sub-task matters")


class PlanOut(BaseModel):
    tasks: list[PlannedTask]


class ResearchTask(BaseModel):
    id: str
    query: str
    rationale: str = ""


# ---------------------------------------------------------------- research


class SearchResult(BaseModel):
    title: str
    url: str
    snippet: str = ""
    content: str = ""  # fetched page text; dropped before it reaches graph state
    score: float | None = None
    published: str | None = None

    @property
    def evidence(self) -> str:
        return self.content or self.snippet


class KeyPoint(BaseModel):
    text: str = Field(description="One factual claim, grounded in the given sources")
    source_urls: list[str] = Field(description="URLs (from the sources) that support the claim")
    quote: str = Field(
        default="",
        description="A short VERBATIM excerpt (<= 300 chars) from one cited source that supports the claim",
    )


class TaskFindings(BaseModel):
    """LLM output of a researcher."""

    summary: str
    key_points: list[KeyPoint]


class Finding(BaseModel):
    task: ResearchTask
    summary: str = ""
    key_points: list[KeyPoint] = []
    sources: list[SearchResult] = []
    dropped_claims: int = 0  # claims removed because they could not be verified
    pages_fetched: int = 0
    error: str | None = None


# ---------------------------------------------------------------- analysis


class Source(BaseModel):
    id: int
    title: str
    url: str
    snippet: str = ""
    published: str | None = None
    quotes: list[str] = []  # verified excerpts that support claims


class Insight(BaseModel):
    text: str
    source_ids: list[int] = Field(description="Ids of the numbered sources supporting this insight")


class Analysis(BaseModel):
    insights: list[Insight]
    contradictions: list[str] = Field(
        default=[], description="Places where sources disagree, with source ids"
    )
    gaps: list[str] = Field(default=[], description="Important aspects the evidence does not cover")
    followup_queries: list[str] = Field(
        default=[], description="Search queries that would fill the most important gaps (max 2)"
    )


# ---------------------------------------------------------------- critique / report


class Critique(BaseModel):
    approved: bool
    issues: list[str] = Field(default=[], description="Concrete problems the writer must fix")


class CitationCheck(BaseModel):
    cited_ids: list[int] = []
    invalid_ids: list[int] = []  # cited but not in the source registry (hallucinated)
    uncited_paragraphs: int = 0  # substantive paragraphs without any citation
    coverage: float = 0.0  # fraction of sources actually cited

    @property
    def ok(self) -> bool:
        return bool(self.cited_ids) and not self.invalid_ids and self.uncited_paragraphs == 0


class JudgeScore(BaseModel):
    coherence: int = Field(ge=1, le=5, description="1 = incoherent, 5 = clear and well structured")
    reasoning: str = ""


class Report(BaseModel):
    question: str
    status: Literal["complete", "insufficient_evidence", "rejected"]
    markdown: str
    sources: list[Source] = []
    insights: list[Insight] = []
    contradictions: list[str] = []
    gaps: list[str] = []
    citation_check: CitationCheck = CitationCheck()
    critic_approved: bool | None = None
    drafts: int = 0
    rounds: int = 0
    dropped_claims: int = 0
    warnings: list[str] = []  # degraded-quality signals the reader should know about
    errors: list[str] = []
    usage: dict[str, int] = {}
