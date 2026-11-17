"""Evaluation cases. Provide your own with ``mars eval --dataset cases.json``."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel


class EvalCase(BaseModel):
    question: str
    expected_topics: list[str] = []  # terms a good report should mention


DEFAULT_CASES = [
    EvalCase(
        question="Compare the current approaches to RAG evaluation",
        expected_topics=["faithfulness", "retrieval", "ragas"],
    ),
    EvalCase(
        question="Pros and cons of microservices vs modular monoliths",
        expected_topics=["microservices", "monolith", "complexity"],
    ),
]


def load_cases(path: str | None) -> list[EvalCase]:
    if not path:
        return DEFAULT_CASES
    raw = json.loads(Path(path).read_text())
    return [EvalCase.model_validate({"question": c} if isinstance(c, str) else c) for c in raw]
