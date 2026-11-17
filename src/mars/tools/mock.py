"""Deterministic offline search (``MARS_PROVIDER=mock``)."""

from __future__ import annotations

import re

from ..schemas import SearchResult


class MockSearch:
    async def search(self, query: str, max_results: int = 5) -> list[SearchResult]:
        slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")[:40]
        return [
            SearchResult(
                title=f"Mock source {i} for '{query[:40]}' (offline)",
                url=f"https://example.org/mock/{slug}/{i}",
                snippet=f"Placeholder evidence #{i} about {query[:60]}.",
            )
            for i in range(1, min(max_results, 3) + 1)
        ]
