import asyncio

import pytest

from mars.core.cache import TTLCache
from mars.core.resilience import retry
from mars.core.text import clean_text, quote_supported

EVIDENCE = (
    "Retrieval-augmented generation (RAG) systems are commonly evaluated along two axes: "
    "retrieval quality and answer faithfulness. RAGAS computes faithfulness by checking every "
    "claim in the answer against the retrieved context."
)


def test_clean_text_strips_invisible_and_truncates():
    assert clean_text("a​b\x00c   d\n\n\n\ne") == "abc d\n\ne"
    assert clean_text("word " * 100, 20).endswith("…")


def test_quote_supported_exact_and_normalised():
    assert quote_supported("answer faithfulness. RAGAS computes faithfulness", EVIDENCE)
    assert quote_supported("RAGAS   COMPUTES faithfulness by checking every claim", EVIDENCE)


def test_quote_supported_tolerates_small_drift():
    assert quote_supported("RAGAS computes faithfulness by checking each claim in the answer", EVIDENCE)


def test_quote_rejected_when_fabricated_or_too_short():
    assert not quote_supported("RAGAS was invented in 1987 by a committee of librarians", EVIDENCE)
    assert not quote_supported("RAGAS", EVIDENCE)
    assert not quote_supported("", EVIDENCE)


async def test_retry_succeeds_after_transient_failures():
    calls = 0

    async def flaky():
        nonlocal calls
        calls += 1
        if calls < 3:
            raise ConnectionError("boom")
        return "ok"

    assert await retry(flaky, attempts=3, base_delay=0.001) == "ok"
    assert calls == 3


async def test_retry_gives_up_and_reraises():
    async def always():
        raise ValueError("nope")

    with pytest.raises(ValueError):
        await retry(always, attempts=2, base_delay=0.001)


async def test_retry_only_catches_listed_exceptions():
    calls = 0

    async def bad():
        nonlocal calls
        calls += 1
        raise KeyError("x")

    with pytest.raises(KeyError):
        await retry(bad, attempts=3, base_delay=0.001, retry_on=(ValueError,))
    assert calls == 1


async def test_retry_does_not_swallow_cancellation():
    async def slow():
        await asyncio.sleep(10)

    task = asyncio.create_task(retry(slow, attempts=3, base_delay=0.001))
    await asyncio.sleep(0.01)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def test_ttl_cache_expiry_and_lru(monkeypatch):
    now = [100.0]
    monkeypatch.setattr("mars.core.cache.time.monotonic", lambda: now[0])
    cache: TTLCache[int] = TTLCache(ttl=10, maxsize=2)
    cache.set("a", 1)
    cache.set("b", 2)
    cache.set("c", 3)  # evicts "a"
    assert cache.get("a") is None and cache.get("b") == 2
    now[0] += 11
    assert cache.get("b") is None
    assert TTLCache(ttl=0).get("x") is None
