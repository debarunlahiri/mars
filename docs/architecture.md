# Architecture

```
src/mars/
  core/       config, logging (run-id correlation), retry/backoff, TTL cache, text utils + quote check, usage counters, errors
  llm/        LLM protocol, LangChain wrapper (timeouts, retries, usage), offline MockLLM
  storage/    ReportStore + vector index (Postgres/pgvector, SQLite), embedders
  tools/      search (Tavily/DDG + fallback + cache + cleaning), page fetcher (SSRF guard, robots, size caps), SSRF validator
  agents/     planner, researcher, analyst, writer, critic  (pure functions over Deps)
  workflow/   state, graph (LangGraph wiring), service (streaming, timeouts, load accounting), deps (wiring)
  api/        FastAPI app factory, routes, auth + rate limiting, request/response models
  evaluation/ metrics and datasets
  cli.py      mars ask | serve | eval | doctor
  schemas.py  Pydantic models passed between agents
  prompts.py  prompts and input formatters
```

Dependency direction: `api/cli -> workflow -> agents -> tools/llm -> core`. `agents` receive a `Deps`
bundle and never construct clients themselves, which is why every agent is unit-testable with fakes.

## Evidence pipeline (why reports can be trusted more than raw LLM output)

1. **Search** returns URLs; results are canonicalised (tracking params stripped), deduplicated and
   filtered against a domain blocklist.
2. **Fetch** reads the top-k pages (public http(s) only, redirects re-validated, 1.5 MB cap,
   robots.txt honoured) and extracts the article text.
3. **Extract**: the researcher must return, per claim, the URL(s) and a verbatim *quote*.
   `quote_supported` checks the quote against that page's text; failing claims are dropped and counted.
4. **Register**: the analyst code assigns citation ids to URLs. The LLM can only cite those ids;
   invented ids are stripped.
5. **Write + critique**: the report cites `[n]`; deterministic checks reject missing/invalid
   citations and uncited paragraphs; the reference list is generated from the registry.
6. **Warn**: the report carries `warnings` (failed tasks, dropped claims, single-domain evidence,
   critic not satisfied) so consumers can decide how far to trust it.

Web text is fenced in `<source>` tags, stripped of control characters, and the prompts tell the
model it is untrusted. A prompt injection can at most make a researcher emit a claim, and that claim
still has to be backed by a quote that exists in the page.

## Known limits

- Quote verification proves a claim was *stated by the source*, not that the source is correct.
- Pages that need JavaScript, paywalls and PDFs are not read (snippet only). Verification is then
  weaker because snippets are short.
- SSRF check resolves DNS before connecting; a hostile DNS server could rebind in between.
- Rate limiting and run accounting are per process; use a gateway/Redis for multi-worker deployments.
- Vector search quality depends on the embedder; the offline hash embedder is lexical only.
- Stored reports are shared across API keys (no tenant isolation) and never expire automatically.
