from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator

from ..core.text import clean_text
from ..schemas import Report


class ResearchRequest(BaseModel):
    question: str = Field(min_length=5, max_length=1000)
    require_approval: bool = Field(default=False, description="Pause after analysis until a human approves")

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
