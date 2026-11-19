"""Researcher: search, read the pages, and extract key points that are *verified* against the text."""

from __future__ import annotations

import asyncio

from ..core.logging import get_logger
from ..core.text import clean_text, quote_supported
from ..prompts import RESEARCHER_SYSTEM, researcher_user, stamped
from ..schemas import Finding, KeyPoint, ResearchTask, SearchResult, TaskFindings
from ..tools.search import canonical_url
from ..workflow.deps import Deps

log = get_logger("researcher")


async def _read_pages(deps: Deps, results: list[SearchResult]) -> tuple[list[SearchResult], int]:
    """Attach full page text to the top-k results (best effort; failures keep the snippet)."""
    if deps.fetcher is None:
        return results, 0
    k = deps.settings.fetch_top_k
    texts = await asyncio.gather(*(deps.fetcher.fetch(r.url) for r in results[:k]))
    enriched = [
        r.model_copy(update={"content": text or ""}) for r, text in zip(results[:k], texts, strict=False)
    ] + results[k:]
    return enriched, sum(1 for t in texts if t)


async def _recall(deps: Deps, query: str, current: list[SearchResult]) -> list[SearchResult]:
    """Reuse verified quotes from earlier research as extra (clearly labelled) evidence."""
    s = deps.settings
    if deps.storage is None or not s.use_memory:
        return []
    try:
        hits = await deps.storage.search(query, k=s.memory_top_k * 3, min_score=s.memory_min_score)
    except Exception as exc:  # noqa: BLE001 - memory is a bonus, never a failure
        log.warning("memory recall failed: %s: %s", type(exc).__name__, str(exc)[:150])
        return []
    have = {canonical_url(r.url) for r in current}
    grouped: dict[str, SearchResult] = {}
    for h in hits:
        url = canonical_url(h.url)
        if url in have:
            continue
        if url in grouped:
            grouped[url].snippet += "\n" + h.text
        elif len(grouped) < s.memory_top_k:
            grouped[url] = SearchResult(
                title=f"{h.title} (earlier research, indexed {h.indexed_at:%Y-%m-%d})",
                url=url,
                snippet=h.text,
                score=h.score,
            )
    return list(grouped.values())


async def _internal(deps: Deps, query: str, doc_ids: list[str] | None = None) -> list[SearchResult]:
    """Passages from the user's indexed documents (best effort, never a failure)."""
    if deps.docs is None or not deps.settings.use_documents:
        return []
    try:
        return await deps.docs.evidence(query, doc_ids)
    except Exception as exc:  # noqa: BLE001
        log.warning("document search failed: %s: %s", type(exc).__name__, str(exc)[:150])
        return []


def _verify(key_points: list[KeyPoint], results: list[SearchResult]) -> tuple[list[KeyPoint], int]:
    """Hallucination control: keep a claim only if it cites a retrieved URL AND its quote is
    actually found in that source's text. Returns (verified points, number dropped)."""
    evidence = {canonical_url(r.url): r.evidence for r in results}
    kept: list[KeyPoint] = []
    dropped = 0
    for kp in key_points:
        urls = [canonical_url(u) for u in dict.fromkeys(kp.source_urls)]
        urls = [u for u in urls if u in evidence]
        quote = clean_text(kp.quote, 400)
        if kp.text.strip() and urls and any(quote_supported(quote, evidence[u]) for u in urls):
            kept.append(KeyPoint(text=kp.text.strip(), source_urls=urls, quote=quote))
        else:
            dropped += 1
    return kept, dropped


async def research(deps: Deps, question: str, task: ResearchTask, scope: dict | None = None) -> Finding:
    # Failures are data, not exceptions: one bad task must not sink the whole run.
    try:
        async with deps.sem:  # bounds parallel search + fetch + LLM pressure
            scope = scope or {}
            internal = await _internal(deps, task.query, scope.get("document_ids") or None)
            results: list[SearchResult] = []
            if scope.get("web", deps.settings.web_search):
                try:
                    results = await deps.search.search(task.query, deps.settings.max_results)
                except Exception as exc:  # noqa: BLE001
                    if not internal:
                        raise
                    log.warning("web search failed, using internal documents only: %s", exc)
            memory = await _recall(deps, task.query, results)
            if not results and not memory and not internal:
                return Finding(task=task, error="search returned no results")
            results, fetched = await _read_pages(deps, results)
            # The user's own documents come first so they win the evidence budget.
            results = internal + results + memory
            out = await deps.fast.structured(
                TaskFindings,
                stamped(RESEARCHER_SYSTEM),
                researcher_user(question, task.query, results, deps.settings.max_evidence_chars),
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("task %s failed: %s: %s", task.id, type(exc).__name__, str(exc)[:200])
        return Finding(task=task, error=f"{type(exc).__name__}: {str(exc)[:200]}")

    kept, dropped = _verify(out.key_points, results)
    log.info(
        "task %s: %d sources (%d pages read), %d claims kept, %d dropped",
        task.id,
        len(results),
        fetched,
        len(kept),
        dropped,
    )
    # Page text is not kept in graph state (large); the verified quotes are.
    slim = [r.model_copy(update={"content": ""}) for r in results]
    return Finding(
        task=task,
        summary=out.summary,
        key_points=kept,
        sources=slim,
        dropped_claims=dropped,
        pages_fetched=fetched,
    )
