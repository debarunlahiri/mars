"""API-key authentication and a small in-memory rate limiter."""

from __future__ import annotations

import hashlib
import hmac
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from ..core.config import Settings


def _presented_key(request: Request) -> str | None:
    key = request.headers.get("x-api-key")
    if key:
        return key
    auth = request.headers.get("authorization", "")
    return auth[7:] if auth.lower().startswith("bearer ") else None


def authenticate(request: Request, settings: Settings) -> str:
    """Return the caller identity (hashed key id, or client IP when auth is disabled)."""
    keys = settings.api_key_list
    if not keys:
        return request.client.host if request.client else "anonymous"
    presented = _presented_key(request) or ""
    # Compare against every key (constant time per comparison) to avoid early-exit timing leaks.
    ok = False
    for k in keys:
        ok |= hmac.compare_digest(presented.encode(), k.encode())
    if not ok:
        raise HTTPException(401, "Missing or invalid API key", headers={"WWW-Authenticate": "Bearer"})
    return "key:" + hashlib.sha256(presented.encode()).hexdigest()[:12]


class RateLimiter:
    """Sliding window, per identity. Single-process only; use a gateway/Redis for multi-worker."""

    def __init__(self, per_minute: int, window: float = 60.0):
        self.limit = per_minute
        self.window = window
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, identity: str) -> None:
        if self.limit <= 0:
            return
        now = time.monotonic()
        hits = self._hits[identity]
        while hits and hits[0] <= now - self.window:
            hits.popleft()
        if len(hits) >= self.limit:
            retry_after = max(1, int(self.window - (now - hits[0])))
            raise HTTPException(429, "Rate limit exceeded", headers={"Retry-After": str(retry_after)})
        hits.append(now)
        if len(self._hits) > 10_000:  # bound memory: forget idle identities
            for k in [k for k, v in self._hits.items() if not v or v[-1] <= now - self.window]:
                del self._hits[k]
