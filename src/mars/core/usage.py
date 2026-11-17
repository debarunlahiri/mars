"""Per-run usage counters (LLM calls/tokens, searches, pages) shared via a context variable."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import asdict, dataclass


@dataclass
class Usage:
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    searches: int = 0
    pages_fetched: int = 0
    cache_hits: int = 0

    def snapshot(self) -> dict[str, int]:
        return asdict(self)


usage_var: ContextVar[Usage | None] = ContextVar("mars_usage", default=None)


def track(**counts: int) -> None:
    """Add to the current run's counters; a no-op outside a run."""
    usage = usage_var.get()
    if usage is None:
        return
    for name, n in counts.items():
        setattr(usage, name, getattr(usage, name) + n)
