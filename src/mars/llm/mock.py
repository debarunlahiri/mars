"""Deterministic offline LLM, for tests and key-less demos (``MARS_PROVIDER=mock``)."""

from __future__ import annotations

import re
from typing import TypeVar

from pydantic import BaseModel

from ..schemas import (
    Analysis,
    Critique,
    Insight,
    JudgeScore,
    KeyPoint,
    PlannedTask,
    PlanOut,
    TaskFindings,
)

T = TypeVar("T", bound=BaseModel)

_SOURCE = re.compile(r'<source url="(.*?)" title="(.*?)">\n(.*?)\n</source>', re.DOTALL)
_POINT = re.compile(r"^- sources=([\d,]+) \| (.*)$", re.MULTILINE)
_INSIGHT = re.compile(r"^- INSIGHT \| sources=([\d,]+) \| (.*)$", re.MULTILINE)


def _question(user: str) -> str:
    m = re.search(r"(?:Research question|Overall question): (.*)", user)
    return m.group(1).strip() if m else "the topic"


def _ids(raw: str) -> list[int]:
    return [int(x) for x in raw.split(",") if x]


class MockLLM:
    name = "mock"

    async def structured(self, schema: type[T], system: str, user: str) -> T:
        q = _question(user)
        if schema is PlanOut:
            angles = ["overview and key concepts", "evidence and benchmarks", "risks and criticisms"]
            return PlanOut(  # type: ignore[return-value]
                tasks=[PlannedTask(query=f"{q} {a}", rationale=a) for a in angles]
            )
        if schema is TaskFindings:
            sources = _SOURCE.findall(user)
            return TaskFindings(  # type: ignore[return-value]
                summary=f"{len(sources)} sources reviewed.",
                key_points=[
                    KeyPoint(text=body.strip(), source_urls=[url], quote=body.strip()[:200])
                    for url, _title, body in sources[:3]
                ],
            )
        if schema is Analysis:
            points = _POINT.findall(user)
            return Analysis(  # type: ignore[return-value]
                insights=[Insight(text=t, source_ids=_ids(ids)) for ids, t in points[:6]],
                gaps=["Offline mock mode: no real-world evidence was consulted."],
            )
        if schema is Critique:
            return Critique(approved=True)  # type: ignore[return-value]
        if schema is JudgeScore:
            return JudgeScore(coherence=4, reasoning="mock")  # type: ignore[return-value]
        raise NotImplementedError(f"MockLLM cannot produce {schema.__name__}")

    async def text(self, system: str, user: str) -> str:
        q = _question(user)
        insights = _INSIGHT.findall(user)
        body = "\n\n".join(
            f"{text.rstrip('.')} " + "".join(f"[{i}]" for i in _ids(ids)) + "." for ids, text in insights
        )
        return (
            f"## Summary\n\nOffline mock report for: {q}\n\n## Findings\n\n{body}\n\n"
            "## Caveats & open questions\n\nGenerated without a real LLM or live search."
        )
