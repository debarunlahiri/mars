# MARS — Multi-Agent Research System

Give it a question; it plans, researches the live web in parallel, **reads the actual pages**, verifies every claim against the source text, and writes a cited Markdown report that a critic reviews. Built with **LangGraph + FastAPI**; works with Anthropic, OpenAI or Gemini, and runs fully offline in mock mode.

```mermaid
flowchart TD
    Q([Question]) --> P[Planner]
    P --> R["Researchers x N, in parallel<br/>search, read pages, extract claims + quotes, verify"]
    R --> A[Analyst]
    A -->|"gaps found and budget left"| R
    A -->|"require_approval"| H{{"Human approval"}}
    A -->|"default"| W[Writer]
    H -->|approved| W
    H -->|rejected| F([Report])
    W --> C[Critic]
    C -->|"issues found and budget left"| W
    C -->|"approved or budget spent"| F
    A -->|"no usable evidence"| F
```

The same flow as plain text, for viewers that do not render Mermaid:

```
Question
   |
   v
Planner
   |
   v
Researchers x N (parallel)  <---------+
  search > read pages >               |  gaps found
  claims + quotes > verify            |  and budget left
   |                                  |
   v                                  |
Analyst ------------------------------+
   |
   +--- require_approval ---> Human approval --- rejected ---> Report
   |                               |
   | (default)                     | approved
   v                               v
Writer <---------------------------+
   |  ^
   v  |  issues found and budget left
Critic
   |  approved or budget spent
   v
Report
```

| Agent | Role | Model tier |
|---|---|---|
| Planner | Splits the question into ≤ `MAX_TASKS` independent search queries | fast |
| Researcher | One per task, in parallel: search, read top pages, extract claims **with verbatim quotes**, drop unverifiable ones | fast |
| Analyst | Merges sources into one numbered registry, cross-checks, lists contradictions/gaps, requests follow-up queries | strong |
| Writer | Writes the report using only the analyst's insights, citing `[n]` | strong |
| Critic | LLM review **plus** deterministic citation checks; sends the draft back if it fails | strong |

## Requirements

Python 3.11+, one LLM API key (Anthropic, OpenAI or Google) for real research, and optionally a [Tavily](https://tavily.com) key (DuckDuckGo is used without one). Postgres with the `pgvector` extension is optional. Docker is optional.

## Quick start

```bash
make install                         # venv + editable install (Anthropic + dev tools)
cp .env.example .env                 # add ONE of ANTHROPIC_API_KEY / GOOGLE_API_KEY / OPENAI_API_KEY (+ optional TAVILY_API_KEY)
.venv/bin/mars doctor                # verifies LLM, search and page fetching with your real keys

.venv/bin/mars ask "Compare the current approaches to RAG evaluation"
.venv/bin/mars ask "Microservices vs modular monoliths in 2026" --approve   # human-in-the-loop
.venv/bin/mars serve                 # API on :8000
.venv/bin/mars eval --dataset data/eval.json
make test                            # 79 tests, offline (incl. an embedded real Postgres+pgvector)
```

Not using `make`? `python3 -m venv .venv && .venv/bin/pip install -e ".[anthropic,dev]"` does the same. Use `.[google,dev]` for Gemini or `.[openai,dev]` for OpenAI.

**Using Gemini:** install the `google` extra, put `GOOGLE_API_KEY=...` in `.env` and set `MARS_PROVIDER=google_genai`. Defaults are `gemini-3.5-flash-lite` (planner, researchers) and `gemini-3.8-flash` (analyst, writer, critic), with Google embeddings (`gemini-embedding-001`, 768 dimensions) for storage. Gemini model names change quickly and old ones stop working for new accounts; if `mars doctor` reports a 404 for a model, pick a current one with `MARS_FAST_MODEL` / `MARS_STRONG_MODEL`. Keys stay in `.env`, which is git-ignored.

With no API keys, `MARS_PROVIDER=auto` falls back to a deterministic **mock** LLM and search (placeholder text, not real research). Set `MARS_PROVIDER=mock MARS_SEARCH_PROVIDER=ddg` to exercise real web search and page reading without an LLM key.

## What makes it work on real-world data

| Problem with real data | What MARS does |
|---|---|
| Search snippets are too thin to support claims | Fetches and extracts the main text of the top pages (`trafilatura`), with size/time caps |
| LLMs fabricate or misattribute claims | Each claim needs URL(s) **and a verbatim quote**; quotes are fuzzy-matched to the page text and unverifiable claims are dropped (`dropped_claims`) |
| Web pages contain prompt injections | Web text is fenced as untrusted, stripped of control chars, cannot close its own fence; injected claims still need a real supporting quote |
| Fetching arbitrary URLs is an SSRF risk | Only public http(s); private/loopback/link-local/metadata IPs blocked; every redirect hop re-validated; robots.txt honoured |
| Search providers rate-limit or fail | Retries with backoff + jitter, Tavily → DuckDuckGo fallback, DuckDuckGo calls serialised and spaced (it throttles bursts), result dedupe/tracking-param stripping, domain blocklist, TTL cache. DuckDuckGo is still best-effort; set `TAVILY_API_KEY` for dependable search |
| LLM calls time out or return malformed JSON | Per-call timeout, retries on malformed structured output, usage tracking; the LLM critic degrades to deterministic checks if it keeps failing |
| One bad source/task shouldn't kill a run | Failures become per-task errors; the report includes `warnings` (failed tasks, dropped claims, single-domain evidence, critic not satisfied) |
| Runs can hang or cost too much | Run deadline, bounded rounds/revisions/tasks/concurrency, token + call + page counters in `report.usage` |
| "Latest" / "in 2026" questions | Current date is injected into every prompt; source publish dates are carried through when the search provider supplies them |

## API

Full reference with schemas, SSE events, errors and client examples: **[docs/api.md](docs/api.md)**. A running server also serves interactive docs at `/docs` (Swagger UI) and `/redoc`.

| Endpoint | Purpose |
|---|---|
| `POST /research` | Blocking. Body: `{"question": "...", "require_approval": false}` |
| `POST /research/stream` | Server-Sent Events: `started`, `step` (per node), `awaiting_approval`, `report`, `error` |
| `POST /research/{thread_id}/approve` | Resume a paused run: `{"approved": true, "feedback": "focus on cost"}` |
| `POST /research/{thread_id}/approve/stream` | Same, as SSE |
| `GET /reports`, `GET /reports/{id}`, `DELETE /reports/{id}` | Stored reports (needs storage configured, else 501) |
| `GET /memory/search?q=...&k=5` | Semantic search over verified quotes from all stored reports |
| `POST /documents` (multipart `files`), `GET /documents`, `GET /documents/search`, `DELETE /documents/{id}` | Internal documents (needs `MARS_DOCS_DB`, else 501) |
| `GET /documents/sync`, `POST /documents/sync` | Auto-sync status / scan the watched folder now |
| `GET /health` | Provider, search backend, storage mode, active runs (unauthenticated) |

Errors are `{"code", "detail"}` with meaningful statuses: 401 bad key, 404 unknown thread, 422 invalid input, 429 rate limited, 503 busy (`Retry-After` set), 504 run timeout. Unexpected failures return a generic message plus an `error_id` that matches the server log; internals are never leaked.

```bash
curl -N -X POST localhost:8000/research/stream -H 'content-type: application/json' \
  -H 'X-API-Key: <your key>' \
  -d '{"question": "Compare the current approaches to RAG evaluation"}'
```

**Production settings:** set `MARS_API_KEYS`, `MARS_DATABASE_URL` (Postgres, so reports and paused approvals survive restarts; `MARS_CHECKPOINT_DB` is the SQLite alternative for checkpoints only), `MARS_LOG_JSON=true`, and put it behind TLS.

## Internal documents + GPU

MARS can research your own files alongside the web. Enable it with `MARS_DOCS_DB=./mars-docs.db`, then upload through the API (`POST /documents`) or the CLI:

```bash
pip install -e '.[documents]'      # pypdf, python-docx, python-pptx, openpyxl
mars ingest ./reports ./slides.pptx ./budget.xlsx ./whiteboard.png
mars ask "What did our Q3 report conclude about churn, and how does that compare with industry trends?"
```

| Format | How it is read |
|---|---|
| PDF | text layer per page; scanned pages go through the vision LLM / OCR |
| Word `.docx` | headings, paragraphs, tables, embedded images |
| PowerPoint `.pptx` | per-slide text, tables, speaker notes, pictures |
| Excel `.xlsx` | per-sheet rows, each value tagged with its column header |
| Images (PNG/JPEG/WebP/GIF/BMP/TIFF) | vision LLM transcribes text and describes charts; `pip install '.[ocr]'` is the offline fallback |
| Text, Markdown, CSV, JSON, HTML | decoded directly |

Passages are embedded, indexed, and handed to the researchers **before** web results. They go through the same quote verification as web pages, so an internal claim is kept only if its quote is really in the file. Sources appear as `doc://<id>/<file>` with the page/slide/sheet in the quoted passage. Set `MARS_WEB_SEARCH=false` to answer from your documents only. Uploaded text is treated as untrusted, like web text.

**Auto-sync.** Set `MARS_DOCS_DIR=./knowledge` and drop files in that folder: the server scans it at startup and every `MARS_DOCS_SYNC_INTERVAL` seconds, indexes new files, re-indexes changed ones and removes deleted or renamed ones, with no manual step. Files whose content is already indexed are skipped, and a file that failed is retried only after it changes. `GET /documents/sync` shows status and the last result, `POST /documents/sync` (or `mars sync`) scans immediately. Files uploaded through the API are never touched by the sync. An index created by an older version is migrated automatically on startup.

**GPU.** Local embedding models run on an NVIDIA GPU (`cuda`) or the Mac's GPU (`mps`) automatically (`MARS_DEVICE=auto|cuda|mps|cpu`). Install `pip install -e '.[gpu]'` and set `MARS_EMBEDDING_PROVIDER=local` (it is picked by `auto` when installed). LLM calls go to the provider's API, so they do not use your GPU. `mars doctor` prints the device in use.

## Configuration

All settings are environment variables prefixed `MARS_` (a `.env` file is loaded automatically); [.env.example](.env.example) lists every option. The ones you will touch first:

| Variable | Default | Meaning |
|---|---|---|
| `MARS_PROVIDER` | `auto` | `anthropic` / `openai` / `google_genai` / `mock`; `auto` picks the first provider whose API key is set, else mock |
| `MARS_FAST_MODEL`, `MARS_STRONG_MODEL` | per provider | Cheap model (planner, researchers) and strong model (analyst, writer, critic) |
| `MARS_SEARCH_PROVIDER` | `auto` | `tavily` (needs `TAVILY_API_KEY`), `ddg`, `mock`; DuckDuckGo is always the fallback |
| `MARS_FETCH_PAGES` | `true` | Read full pages, not just snippets |
| `MARS_MAX_TASKS` / `MAX_ROUNDS` / `MAX_REVISIONS` | `4` / `2` / `2` | Cost and latency bounds |
| `MARS_RUN_TIMEOUT` | `300` | Seconds before a run is aborted (HTTP 504) |
| `MARS_API_KEYS` | empty | Comma-separated keys; **empty means no authentication** |
| `MARS_DATABASE_URL` | empty | Postgres + pgvector for reports, vectors and checkpoints |
| `MARS_STORAGE_DB` | empty | SQLite file for reports + vectors when there is no Postgres |
| `MARS_USE_MEMORY` | `false` | Reuse verified quotes from earlier reports |
| `MARS_DOCS_DB` | empty | SQLite file for the internal-document index; **empty disables documents** |
| `MARS_DOCS_DIR` / `MARS_DOCS_SYNC_INTERVAL` | empty / `30` | Folder kept in sync with the index automatically (add, update, remove) / seconds between scans |
| `MARS_USE_DOCUMENTS` | `true` | Researchers search the indexed documents |
| `MARS_WEB_SEARCH` | `true` | `false` answers from your documents only |
| `MARS_DOCS_TOP_K` / `MARS_DOCS_MIN_SCORE` | `4` / `0.15` | Documents given to a researcher / minimum similarity |
| `MARS_MAX_UPLOAD_MB` | `25` | Per-file upload limit |
| `MARS_VISION_IMAGES` | `true` | Read images and scanned pages with the LLM |
| `MARS_DEVICE` | `auto` | `auto` / `cuda` (NVIDIA) / `mps` (Apple GPU) / `cpu` for local embedding models |
| `MARS_EMBEDDING_PROVIDER` | `auto` | `hash` / `openai` / `google` / `fastembed` / `local` (GPU-capable, needs `.[gpu]`) |

## Storage: Postgres + vector search

Set `MARS_DATABASE_URL=postgresql://...` and MARS keeps **everything** in one Postgres:

| What | Where |
|---|---|
| Finished reports (full JSON, queryable) | `mars_reports` |
| Verified source quotes + embeddings | `mars_chunks` (`pgvector`, HNSW cosine index) |
| In-flight / paused (awaiting approval) runs | LangGraph checkpoint tables |

No Postgres? `MARS_STORAGE_DB=./mars-data.db` gives the same reports + vector search in one SQLite file (exact search; fine up to ~100k quotes). Only reports with status `complete` are stored, and only quotes that passed verification are indexed.

- **Memory:** with `MARS_USE_MEMORY=true`, researchers also pull relevant quotes from earlier research and treat them as extra, clearly labelled evidence ("earlier research, indexed 2026-11-17"). They go through the same quote verification and are always ranked after fresh web results.
- **Embeddings:** `auto` uses OpenAI embeddings if `OPENAI_API_KEY` is set, otherwise local `fastembed` if installed (`pip install -e ".[local-embeddings]"`), otherwise an offline **hash** embedder that only matches shared words, not paraphrases. Anthropic has no embeddings API. The embedding model/dimension is recorded in the database; switching models later is refused with an explanation rather than silently mixing vectors.
- **Docker:** `docker compose up --build` starts `pgvector/pgvector:pg16` and points MARS at it.
- **Your own Postgres:** the role needs permission to run `CREATE EXTENSION vector` once (or have an admin do it), then `MARS_DATABASE_URL=postgresql://user:pass@host:5432/mars`. Tables are created on startup.
- CLI: `mars reports` lists stored reports; `mars memory "hybrid retrieval recall"` searches them.

## Design decisions

- **Parallel vs sequential.** Planner sub-tasks are independent, so they fan out with LangGraph `Send` (bounded by `MAX_CONCURRENCY`). Dependencies are handled by *rounds*: the analyst can request up to two follow-up queries, run in parallel as a second round. Analyst → writer → critic is inherently sequential.
- **State.** One typed `ResearchState`; parallel findings merge via a list-append reducer; every handoff is a validated Pydantic model. Page text is dropped before state is checkpointed.
- **Cost & latency.** Cheap model for the many planner/researcher calls, strong model for analysis/writing/critique; hard budgets on tasks, results, pages, rounds, revisions and wall-clock time.
- **Human-in-the-loop.** With `require_approval` the graph pauses (`interrupt`) after analysis and resumes on `/approve` with optional writer guidance. A rejection ends the run without writing.
- **Evaluation.** `mars eval` scores citations present/valid, no uncited claims, source coverage, a lexical faithfulness proxy, expected-topic coverage, structure, and an LLM-judged coherence score.
- **Observability.** Run-id-correlated logs (JSON optional), per-run usage counters, `X-Request-ID`; set `LANGSMITH_TRACING=true` for LangSmith traces.

## Project structure

```
src/mars/
  core/        config, logging, retry, cache, text/quote verification, usage, errors
  llm/         LLM protocol, LangChain wrapper, offline mock
  tools/       search (+fallback/cache), page fetcher, SSRF guard
  storage/     reports + vector index: Postgres/pgvector and SQLite, embedders
  agents/      planner, researcher, analyst, writer, critic
  workflow/    graph, state, service (streaming/timeouts), deps, runtime (opens DB/checkpointer)
  api/         app factory, routes, auth + rate limit, models
  evaluation/  metrics, datasets
  cli.py       mars ask | serve | eval | doctor | reports | memory
tests/unit/        core, tools, agents, embeddings (no network)
tests/integration/ graph, API, storage (SQLite + embedded Postgres)
data/eval.json     sample evaluation dataset
docs/api.md            API reference (endpoints, events, schemas, examples)
docs/architecture.md   evidence pipeline, dependency direction, known limits
```

## Troubleshooting

| Symptom | Fix |
|---|---|
| `mars doctor` says `llm: FAILED` | Check the provider key in `.env` and that `MARS_FAST_MODEL`/`MARS_STRONG_MODEL` exist for your account |
| Reports contain "offline mock" text | No API key was found, so `MARS_PROVIDER=auto` chose mock; set a key or `MARS_PROVIDER` explicitly |
| Many claims dropped (`dropped_claims`) | Pages could not be read (JS/paywall), so only snippets were checkable; try Tavily, raise `MARS_FETCH_TOP_K`, or ignore if the count is small |
| `pgvector is not available` | Use `pgvector/pgvector:pg16` or run `CREATE EXTENSION vector` as a superuser |
| `indexed with embeddings 'X' but 'Y' is configured` | You changed the embedding model; switch back or point at a fresh database |
| HTTP 503 `busy` / 429 | Raise `MARS_MAX_CONCURRENT_RUNS` / `MARS_RATE_LIMIT_PER_MIN`, or retry after the `Retry-After` header |

## Honest limits

- Quote verification proves a claim was *stated by the source*, not that the source is right. JavaScript-only pages, paywalls and PDFs are not read (snippet only, so weaker verification).
- Rate limiting and active-run accounting are per process. Run one worker, or add a gateway/Redis.
- Stored reports are visible to every API key (no per-user isolation), and nothing expires them automatically; use `DELETE /reports/{id}`. Remembered quotes can go stale, so memory is opt-in and labelled with its indexing date.
- Real LLM calls (Anthropic/OpenAI/Gemini) and Tavily are not covered by the automated tests (no keys in CI); use `mars doctor` and `mars eval` with your keys to validate them.
