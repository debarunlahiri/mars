from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from ..core.text import clean_text
from ..schemas import Report


class ResearchRequest(BaseModel):
    question: str = Field(min_length=5, max_length=1000)
    require_approval: bool = Field(default=False, description="Pause after analysis until a human approves")
    document_ids: list[str] = Field(
        default=[],
        max_length=20,
        description="Indexed documents attached to the question; research reads them first "
        "(see POST /documents). Unknown ids are ignored.",
    )
    web_search: bool | None = Field(
        default=None,
        description="Also search the web. Default: no when documents are attached, else MARS_WEB_SEARCH.",
    )

    @field_validator("question")
    @classmethod
    def _clean(cls, v: str) -> str:
        v = " ".join(clean_text(v).split())
        if len(v) < 5:
            raise ValueError("question is too short")
        return v


class ApprovalRequest(BaseModel):
    approved: bool
    feedback: str = Field(default="", max_length=2000, description="Guidance for the writer")


class ResearchResponse(BaseModel):
    thread_id: str
    status: str  # complete | insufficient_evidence | rejected | awaiting_approval
    report: Report | None = None
    preview: dict[str, Any] | None = None


class ErrorResponse(BaseModel):
    code: str
    detail: str
