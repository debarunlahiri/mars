"""Retry with exponential backoff + jitter."""

from __future__ import annotations

import asyncio
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

from .logging import get_logger

T = TypeVar("T")
log = get_logger("resilience")


async def retry(
    fn: Callable[[], Awaitable[T]],
    *,
    attempts: int = 3,
    base_delay: float = 0.5,
    max_delay: float = 8.0,
    retry_on: tuple[type[BaseException], ...] = (Exception,),
    name: str = "operation",
) -> T:
    """Call ``fn`` up to ``attempts`` times. Cancellation is never swallowed."""
    for attempt in range(1, attempts + 1):
        try:
            return await fn()
        except retry_on as exc:
            if attempt == attempts:
                raise
            delay = min(max_delay, base_delay * 2 ** (attempt - 1)) * random.uniform(0.5, 1.0)
            log.warning(
                "%s failed (%s: %s); retry %d/%d in %.1fs",
                name,
                type(exc).__name__,
                str(exc)[:120],
                attempt,
                attempts - 1,
                delay,
            )
            await asyncio.sleep(delay)
    raise AssertionError("unreachable")  # pragma: no cover
