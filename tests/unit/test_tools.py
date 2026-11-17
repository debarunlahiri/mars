import httpx
import pytest

from mars.core.config import Settings
from mars.core.errors import SearchError, UnsafeURL
from mars.schemas import SearchResult
from mars.tools.fetch import PageFetcher
from mars.tools.search import ResilientSearch, canonical_url, clean_results
from mars.tools.security import assert_public_url

ARTICLE = (
    "<html><head><title>t</title><script>evil()</script></head><body><nav>menu</nav><article>"
    "<h1>Title</h1>"
    + "<p>RAG evaluation measures faithfulness and retrieval quality. </p>" * 12
    + "</article></body></html>"
)


# ------------------------------------------------------------ SSRF guard
@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/",
        "http://localhost:8000/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "http://[::ffff:127.0.0.1]/",
        "file:///etc/passwd",
        "ftp://example.com/x",
        "http://user:pass@example.com/",
    ],
)
async def test_assert_public_url_blocks(url):
    with pytest.raises(UnsafeURL):
        await assert_public_url(url)


async def test_assert_public_url_allows_public_ip():
    await assert_public_url("https://93.184.216.34/page")


# ------------------------------------------------------------ fetcher
def _fetcher(handler, **overrides) -> PageFetcher:
    async def allow(_url: str) -> None:
        return None

    s = Settings(provider="mock", respect_robots=False, **overrides)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return PageFetcher(s, client=client, validate=allow)


async def test_fetch_extracts_main_text_and_drops_boilerplate():
    f = _fetcher(lambda r: httpx.Response(200, text=ARTICLE, headers={"content-type": "text/html"}))
    text = await f.fetch("https://example.com/a")
    assert text and "faithfulness" in text
    assert "evil()" not in text and "menu" not in text


async def test_fetch_skips_non_html_and_http_errors():
    pdf = _fetcher(
        lambda r: httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})
    )
    assert await pdf.fetch("https://example.com/a.pdf") is None
    err = _fetcher(lambda r: httpx.Response(503))
    assert await err.fetch("https://example.com/down") is None


async def test_fetch_truncates_oversized_pages():
    big = "<html><body><p>" + ("lorem ipsum dolor sit amet " * 200_000) + "</p></body></html>"
    f = _fetcher(
        lambda r: httpx.Response(200, text=big, headers={"content-type": "text/html"}),
        max_page_bytes=50_000,
        max_page_chars=1000,
    )
    text = await f.fetch("https://example.com/big")
    assert text and len(text) <= 1001


async def test_fetch_revalidates_every_redirect_hop():
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://169.254.169.254/latest/meta-data/"})

    s = Settings(provider="mock", respect_robots=False)
    f = PageFetcher(s, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)))
    # real validator, but the first hop must itself pass: use a public IP literal
    assert await f.fetch("http://93.184.216.34/start") is None
    assert seen == ["http://93.184.216.34/start"]  # the metadata address was never requested


async def test_fetch_honours_robots_txt():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(
                200, text="User-agent: *\nDisallow: /private", headers={"content-type": "text/plain"}
            )
        return httpx.Response(200, text=ARTICLE, headers={"content-type": "text/html"})

    async def allow(_url: str) -> None:
        return None

    s = Settings(provider="mock", respect_robots=True)
    f = PageFetcher(s, client=httpx.AsyncClient(transport=httpx.MockTransport(handler)), validate=allow)
    assert await f.fetch("https://example.com/private/x") is None
    assert await f.fetch("https://example.com/public") is not None


async def test_fetch_result_is_cached():
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, text=ARTICLE, headers={"content-type": "text/html"})

    f = _fetcher(handler)
    await f.fetch("https://example.com/a")
    await f.fetch("https://example.com/a")
    assert calls == 1


# ------------------------------------------------------------ search
def _r(url: str, title="t", snippet="s") -> SearchResult:
    return SearchResult(title=title, url=url, snippet=snippet)


def test_canonical_url_strips_tracking_and_fragment():
    assert (
        canonical_url("HTTPS://Example.com/a/?utm_source=x&id=7&fbclid=z#top") == "https://example.com/a?id=7"
    )


def test_clean_results_dedupes_blocks_and_limits():
    raw = [
        _r("https://a.com/x?utm_campaign=1"),
        _r("https://a.com/x/"),
        _r("https://www.pinterest.com/pin/1"),
        _r("javascript:alert(1)"),
        _r("https://b.com"),
        _r("https://c.com"),
    ]
    out = clean_results(raw, ["pinterest.com"], limit=2)
    assert [r.url for r in out] == ["https://a.com/x", "https://b.com"]


class _Stub:
    def __init__(self, results=None, exc=None):
        self.results, self.exc, self.calls = results or [], exc, 0

    async def search(self, query, max_results=5):
        self.calls += 1
        if self.exc:
            raise self.exc
        return self.results


async def test_resilient_search_falls_back_to_next_provider():
    broken, good = _Stub(exc=RuntimeError("quota")), _Stub([_r("https://a.com")])
    s = ResilientSearch([broken, good], attempts=2, base_delay=0.001)
    assert [r.url for r in await s.search("q")] == ["https://a.com"]
    assert broken.calls == 2  # retried before falling back


async def test_resilient_search_caches_and_isolates_copies():
    good = _Stub([_r("https://a.com")])
    s = ResilientSearch([good], base_delay=0.001)
    first = await s.search("Same  Query")
    first[0].content = "mutated"
    second = await s.search("same query")
    assert good.calls == 1 and second[0].content == ""


async def test_resilient_search_raises_when_every_provider_fails():
    s = ResilientSearch([_Stub(exc=RuntimeError("a")), _Stub(exc=RuntimeError("b"))], attempts=1)
    with pytest.raises(SearchError):
        await s.search("q")


async def test_resilient_search_empty_results_is_not_an_error():
    assert await ResilientSearch([_Stub([])], attempts=1).search("q") == []
