"""Dependency container: which models, search backend and fetcher each agent gets."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from ..core.config import Settings, get_settings
from ..llm import LLM, LangChainLLM, MockLLM
from ..storage import Storage
from ..tools import (
    DuckDuckGoSearch,
    MockSearch,
    PageFetcher,
    ResilientSearch,
    SearchTool,
    TavilySearch,
)


@dataclass
class Deps:
    settings: Settings
    fast: LLM  # planner + researchers: many cheap calls
    strong: LLM  # analyst + writer + critic: few high-quality calls
    search: SearchTool
    fetcher: PageFetcher | None = None  # None = snippets only
    storage: Storage | None = None  # durable reports + vector memory (set by the runtime)
    sem: asyncio.Semaphore = field(default_factory=lambda: asyncio.Semaphore(4))

    async def aclose(self) -> None:
        if self.fetcher:
            await self.fetcher.aclose()


def build_search(s: Settings) -> SearchTool:
    backend = s.resolved_search()
    if backend == "mock":
        return MockSearch()
    chain: list[SearchTool] = []
    if backend == "tavily":
        chain.append(TavilySearch())
    chain.append(DuckDuckGoSearch())  # keyless fallback if the primary fails or is exhausted
    if backend == "ddg":
        chain = chain[-1:]
    return ResilientSearch(
        chain,
        s.blocked_domain_list,
        attempts=s.search_attempts,
        cache_ttl=s.search_cache_ttl,
        base_delay=2.0,
    )


def build_deps(settings: Settings | None = None) -> Deps:
    s = settings or get_settings()
    provider = s.resolved_provider()
    fast: LLM
    strong: LLM
    if provider == "mock":
        fast = strong = MockLLM()
    else:
        fast_name, strong_name = s.models()
        kw = dict(
            temperature=s.temperature,
            max_tokens=s.max_tokens,
            timeout=s.llm_timeout,
            attempts=s.llm_attempts,
        )
        fast = LangChainLLM(fast_name, provider, **kw)  # type: ignore[arg-type]
        strong = LangChainLLM(strong_name, provider, **kw)  # type: ignore[arg-type]

    fetcher = PageFetcher(s) if s.fetch_pages and s.resolved_search() != "mock" else None
    return Deps(s, fast, strong, build_search(s), fetcher, sem=asyncio.Semaphore(s.max_concurrency))
