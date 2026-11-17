"""Web search: Tavily / DuckDuckGo behind one interface, with retries, fallback, caching, cleaning."""

from __future__ import annotations

import asyncio
import os
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from ..core.cache import TTLCache
from ..core.errors import SearchError
from ..core.logging import get_logger
from ..core.resilience import retry
from ..core.text import clean_text
from ..core.usage import track
from ..schemas import SearchResult

log = get_logger("search")

_TRACKING_PARAMS = ("utm_", "fbclid", "gclid", "mc_cid", "mc_eid", "ref_", "igshid")


class SearchTool(Protocol):
    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]: ...


def canonical_url(url: str) -> str:
    """Strip fragments and tracking params so the same page is not counted twice."""
    p = urlsplit(url.strip())
    query = urlencode([(k, v) for k, v in parse_qsl(p.query) if not k.lower().startswith(_TRACKING_PARAMS)])
    path = p.path.rstrip("/") or ""
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), path, query, ""))


def clean_results(results: list[SearchResult], blocked_domains: list[str], limit: int) -> list[SearchResult]:
    seen: set[str] = set()
    out: list[SearchResult] = []
    for r in results:
        url = canonical_url(r.url)
        parts = urlsplit(url)
        host = (parts.hostname or "").lower()
        if parts.scheme not in ("http", "https") or not host:
            continue
        if any(host == d or host.endswith("." + d) for d in blocked_domains):
            continue
        if url in seen:
            continue
        seen.add(url)
        out.append(
            r.model_copy(
                update={
                    "url": url,
                    "title": clean_text(r.title, 200) or host,
                    "snippet": clean_text(r.snippet, 1200),
                }
            )
        )
        if len(out) >= limit:
            break
    return out


class TavilySearch:
    URL = "https://api.tavily.com/search"

    def __init__(self, api_key: str | None = None, client: httpx.AsyncClient | None = None):
        self._key = api_key or os.environ["TAVILY_API_KEY"]
        self._client = client

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        client = self._client or httpx.AsyncClient(timeout=30)
        try:
            resp = await client.post(
                self.URL,
                headers={"Authorization": f"Bearer {self._key}"},
                json={"query": query, "max_results": max_results, "search_depth": "advanced"},
            )
            resp.raise_for_status()
        finally:
            if self._client is None:
                await client.aclose()
        return [
            SearchResult(
                title=r.get("title", ""),
                url=r["url"],
                snippet=r.get("content", ""),
                score=r.get("score"),
                published=r.get("published_date"),
            )
            for r in resp.json().get("results", [])
            if r.get("url")
        ]


class DuckDuckGoSearch:
    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        from ddgs import DDGS

        def _run() -> list[dict]:
            return list(DDGS(timeout=15).text(query, max_results=max_results))

        rows = await asyncio.to_thread(_run)
        return [
            SearchResult(title=r.get("title", ""), url=r["href"], snippet=r.get("body", ""))
            for r in rows
            if r.get("href")
        ]


class ResilientSearch:
    """Try providers in order (each with retries); clean, dedupe and cache the results."""

    def __init__(
        self,
        providers: list[SearchTool],
        blocked_domains: list[str] | None = None,
        attempts: int = 2,
        cache_ttl: float = 900.0,
        base_delay: float = 1.0,
    ):
        self.providers = providers
        self.blocked = blocked_domains or []
        self.attempts = attempts
        self.base_delay = base_delay
        self._cache: TTLCache[list[SearchResult]] = TTLCache(cache_ttl)

    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        key = (" ".join(query.lower().split()), max_results)
        if (hit := self._cache.get(key)) is not None:
            track(cache_hits=1)
            return [r.model_copy() for r in hit]

        errors: list[str] = []
        for provider in self.providers:
            name = type(provider).__name__
            try:
                # Over-fetch: cleaning (dedupe/blocklist) removes some results.
                raw = await retry(
                    lambda p=provider: p.search(query, max_results * 2),
                    attempts=self.attempts,
                    base_delay=self.base_delay,
                    name=f"{name}.search",
                )
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{name}: {type(exc).__name__}: {str(exc)[:100]}")
                continue
            results = clean_results(raw, self.blocked, max_results)
            if results:
                track(searches=1)
                self._cache.set(key, results)
                return [r.model_copy() for r in results]
            log.info("%s returned no usable results for %r", name, query)
        if errors and len(errors) == len(self.providers):
            raise SearchError("all search providers failed: " + "; ".join(errors))
        return []
