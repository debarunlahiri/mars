"""Safe, polite page fetching + main-text extraction."""

from __future__ import annotations

import html
import re
from collections.abc import Awaitable, Callable
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import httpx

from ..core.cache import TTLCache
from ..core.config import Settings
from ..core.errors import UnsafeURL
from ..core.logging import get_logger
from ..core.text import clean_text
from ..core.usage import track
from .security import assert_public_url

log = get_logger("fetch")

MAX_REDIRECTS = 3
ALLOWED_TYPES = ("text/html", "application/xhtml", "text/plain")

_TAGS = re.compile(r"(?is)<(script|style|noscript|svg|nav|footer|header|form)[^>]*>.*?</\1>")
_ANY_TAG = re.compile(r"(?s)<[^>]+>")


def extract_text(raw_html: str, limit: int) -> str:
    """Main article text via trafilatura, with a crude tag-stripping fallback."""
    text = ""
    try:
        import trafilatura

        text = trafilatura.extract(raw_html, include_comments=False, include_tables=True) or ""
    except Exception as exc:  # noqa: BLE001
        log.debug("trafilatura failed: %s", exc)
    if len(text) < 200:  # extractor gave up (JS-heavy page, odd markup)
        stripped = _ANY_TAG.sub(" ", _TAGS.sub(" ", raw_html))
        fallback = html.unescape(stripped)
        text = fallback if len(fallback) > len(text) else text
    return clean_text(text, limit)


class PageFetcher:
    def __init__(
        self,
        settings: Settings,
        client: httpx.AsyncClient | None = None,
        validate: Callable[[str], Awaitable[None]] = assert_public_url,
    ):
        self.s = settings
        self._validate = validate
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.fetch_timeout),
            headers={"User-Agent": settings.user_agent, "Accept": "text/html,text/plain;q=0.9"},
        )
        self._cache: TTLCache[str] = TTLCache(settings.search_cache_ttl, maxsize=256)
        self._robots: TTLCache[RobotFileParser | None] = TTLCache(3600, maxsize=256)
        self._no_robots = object()

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch(self, url: str) -> str | None:
        """Extracted page text, or None. Never raises: a bad page must not fail a research task."""
        cached = self._cache.get(url)
        if cached is not None:
            track(cache_hits=1)
            return cached or None
        try:
            if self.s.respect_robots and not await self._allowed(url):
                log.info("robots.txt disallows %s", url)
                self._cache.set(url, "")
                return None
            body, ctype, charset = await self._get(url, self.s.max_page_bytes)
            if not any(ctype.startswith(t) for t in ALLOWED_TYPES):
                raise ValueError(f"unsupported content type {ctype or 'unknown'}")
            raw = _decode(body, charset)
            text = raw if ctype.startswith("text/plain") else extract_text(raw, self.s.max_page_chars)
            text = clean_text(text, self.s.max_page_chars)
        except (TimeoutError, UnsafeURL, httpx.HTTPError, ValueError) as exc:
            log.info("skip %s: %s: %s", url, type(exc).__name__, str(exc)[:100])
            self._cache.set(url, "")
            return None
        except Exception as exc:  # noqa: BLE001
            log.warning("unexpected fetch error for %s: %r", url, exc)
            return None
        if len(text) < 80:
            return None
        track(pages_fetched=1)
        self._cache.set(url, text)
        return text

    async def _get(self, url: str, max_bytes: int) -> tuple[bytes, str, str | None]:
        """GET with manual redirects (each hop re-validated) and a hard size cap."""
        for _ in range(MAX_REDIRECTS + 1):
            await self._validate(url)
            async with self._client.stream("GET", url, follow_redirects=False) as resp:
                if resp.is_redirect:
                    loc = resp.headers.get("location")
                    if not loc:
                        raise ValueError("redirect without location")
                    url = urljoin(url, loc)
                    continue
                resp.raise_for_status()
                chunks: list[bytes] = []
                size = 0
                async for chunk in resp.aiter_bytes():
                    size += len(chunk)
                    chunks.append(chunk)
                    if size >= max_bytes:  # truncate instead of failing: the top of a page is enough
                        break
                ctype = resp.headers.get("content-type", "").split(";")[0].strip().lower()
                return b"".join(chunks)[:max_bytes], ctype, resp.charset_encoding
        raise ValueError("too many redirects")

    async def _allowed(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        cached = self._robots.get(origin)
        if cached is None:  # not cached yet (a cached "no robots.txt" is stored as the sentinel)
            cached = await self._load_robots(origin) or self._no_robots
            self._robots.set(origin, cached)  # type: ignore[arg-type]
        if cached is self._no_robots:
            return True  # no robots.txt (or unreachable): allowed
        return cached.can_fetch(self.s.user_agent, url)  # type: ignore[union-attr]

    async def _load_robots(self, origin: str) -> RobotFileParser | None:
        try:
            body, _, _ = await self._get(f"{origin}/robots.txt", 200_000)
        except Exception:  # noqa: BLE001
            return None
        parser = RobotFileParser()
        parser.parse(body.decode("utf-8", errors="replace").splitlines())
        return parser


def _decode(body: bytes, charset: str | None) -> str:
    try:
        return body.decode(charset or "utf-8", errors="replace")
    except LookupError:  # unknown charset label
        return body.decode("utf-8", errors="replace")
