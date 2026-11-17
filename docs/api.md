# MARS API reference

Base URL: `http://localhost:8000` (`mars serve`). Interactive docs are served by the app itself:
`/docs` (Swagger UI), `/redoc`, and the machine-readable schema at `/openapi.json`.

- [Authentication](#authentication)
- [Conventions and errors](#conventions-and-errors)
- [Run research](#run-research)
- [Streaming (SSE)](#streaming-sse)
- [Human approval](#human-approval)
- [Stored reports](#stored-reports)
- [Memory search](#memory-search)
- [Health](#health)
- [Data models](#data-models)
- [Client examples](#client-examples)

## Authentication

Set `MARS_API_KEYS` (comma-separated) to require a key on every endpoint except `GET /health`. Send it as either:

```
X-API-Key: <key>
Authorization: Bearer <key>
```

If `MARS_API_KEYS` is empty the API is **unauthenticated** (the server logs a warning at startup). Use that for local development only.

## Conventions and errors

- Requests and responses are JSON (`Content-Type: application/json`), except streaming endpoints (`text/event-stream`).
- Every response carries `X-Request-ID` (your `X-Request-ID` header is echoed if you send one).
- Errors from MARS have the body `{"code": "...", "detail": "..."}`.
- Request-validation failures (HTTP 422) use FastAPI's standard body, `{"detail": [{"loc": [...], "msg": "...", "type": "..."}]}`.
- Unexpected failures return `{"code": "internal_error", "detail": "Research failed unexpectedly (error_id=ab12cd34)."}`. The `error_id` matches a line in the server log; internals are never returned.

| HTTP | `code` | Meaning |
|---|---|---|
| 401 | `error` | Missing or invalid API key (`WWW-Authenticate: Bearer`) |
| 404 | `error` | Unknown report, or no run awaiting approval for that `thread_id` |
| 422 | n/a | Invalid input (see above) |
| 429 | `error` | Rate limit exceeded; wait `Retry-After` seconds |
| 500 | `internal_error` | Unexpected failure; quote the `error_id` |
| 501 | `storage_disabled` | Report/memory endpoints called without `MARS_DATABASE_URL` or `MARS_STORAGE_DB` |
| 502 | `search_failed` | Reserved for search failures that abort a run (individual task failures do not abort; see `report.errors`) |
| 503 | `error` | Server busy (`MARS_MAX_CONCURRENT_RUNS` reached); wait `Retry-After` |
| 504 | `run_timeout` | Run exceeded `MARS_RUN_TIMEOUT` seconds |

Limits: each API key (or client IP when auth is disabled) is limited to `MARS_RATE_LIMIT_PER_MIN` requests per minute on research and report endpoints. The limiter is per process.

## Run research

### `POST /research`

Runs the whole pipeline and returns when it is finished (typically 30 to 120 seconds with real models). For progress updates use the [streaming variant](#post-researchstream).

**Request body**

| Field | Type | Default | Notes |
|---|---|---|---|
| `question` | string | required | 5 to 1000 characters after whitespace/control-character cleanup |
| `require_approval` | boolean | `false` | Pause after analysis for a human decision ([see below](#human-approval)) |

**Response `200`**: `ResearchResponse`

| Field | Type | Notes |
|---|---|---|
| `thread_id` | string | Identifies this run; also the stored report's id |
| `status` | string | `complete`, `insufficient_evidence`, `rejected` or `awaiting_approval` |
| `report` | [`Report`](#report) \| null | Present unless `awaiting_approval` |
| `preview` | object \| null | Present only for `awaiting_approval` (see [approval preview](#approval-preview)) |

```bash
curl -s -X POST localhost:8000/research \
  -H 'content-type: application/json' -H 'X-API-Key: $KEY' \
  -d '{"question": "Compare the current approaches to RAG evaluation"}'
```

`status` values:

| Value | Meaning |
|---|---|
| `complete` | A cited report was written. Check `report.warnings` before trusting it fully |
| `insufficient_evidence` | No usable evidence was found; `report.errors` says why. No report is stored |
| `rejected` | A reviewer rejected the research at the approval step |
| `awaiting_approval` | Paused; call [`/approve`](#post-researchthread_idapprove) |

A failure of an individual research task does not fail the request: the task is listed in `report.errors` and the run continues.

### `POST /research/stream`

Same request body as `POST /research`. Returns `text/event-stream`; see [Streaming](#streaming-sse).

## Streaming (SSE)

Each event is `event: <name>` + `data: <json>`, separated by a blank line. The stream always begins with `started` and ends with exactly one of `report`, `awaiting_approval` or `error`.

| Event | `data` fields |
|---|---|
| `started` | `thread_id` |
| `step` | `node` plus node-specific fields (table below) |
| `awaiting_approval` | `thread_id`, `preview` |
| `report` | `thread_id`, `report` ([`Report`](#report)), `stored` (bool: saved to the database) |
| `error` | `thread_id`, `code`, `status` (HTTP-style number), `detail` |

`step` events, in the order they usually occur (`researcher` events arrive in parallel; the analyst/researcher pair can repeat for a follow-up round, and writer/critic repeat per revision):

| `node` | Extra fields |
|---|---|
| `planner` | `tasks`: list of search queries |
| `researcher` | `task`, `sources`, `pages_read`, `claims` (verified), `dropped` (unverifiable), `error` |
| `analyst` | `insights`, `sources`, `followups` (queries for another round) |
| `approval` | `approved` |
| `writer` | `draft` (draft number) |
| `critic` | `approved`, `issues` |
| `finalize` | `status` |

Example stream (abridged):

```
event: started
data: {"event": "started", "thread_id": "081d4fa5..."}

event: step
data: {"event": "step", "node": "researcher", "task": "modular monolith overview", "sources": 5, "pages_read": 3, "claims": 5, "dropped": 0, "error": null}

event: step
data: {"event": "step", "node": "critic", "approved": true, "issues": []}

event: report
data: {"event": "report", "thread_id": "081d4fa5...", "report": {...}, "stored": true}
```

Notes: HTTP errors that happen before streaming starts (401, 422, 429, 503) are normal JSON responses. Failures after the stream has started arrive as an `error` event on a `200` response. If the client disconnects, the server stops the run and frees its slot. Disable proxy buffering for SSE (the response sets `X-Accel-Buffering: no` for nginx).

## Human approval

With `require_approval: true`, the run pauses after the analyst. The response (or stream) ends with `status: "awaiting_approval"` and a `preview` so a person can inspect the evidence before the report is written.

### Approval preview

```json
{
  "message": "Review the research before the report is written.",
  "insights": [{"text": "...", "source_ids": [1, 2]}],
  "gaps": ["..."],
  "contradictions": ["..."],
  "sources": [{"id": 1, "title": "...", "url": "...", "snippet": "...", "published": null, "quotes": ["..."]}]
}
```

### `POST /research/{thread_id}/approve`

Resumes the paused run and returns the final `ResearchResponse` (same shape as `POST /research`).

| Field | Type | Notes |
|---|---|---|
| `approved` | boolean | `false` ends the run with `status: "rejected"` and no report is written |
| `feedback` | string, max 2000 | Optional guidance passed to the writer (for example "focus on cost") |

Returns `404` if `thread_id` is unknown or the run is not waiting (for example it already finished). Paused runs survive a restart only when `MARS_DATABASE_URL` or `MARS_CHECKPOINT_DB` is set.

### `POST /research/{thread_id}/approve/stream`

Same body; returns the SSE stream for the remainder of the run.

## Stored reports

These endpoints need storage (`MARS_DATABASE_URL` for Postgres or `MARS_STORAGE_DB` for SQLite); otherwise they return `501`. Only reports with status `complete` are stored. A report's id is the `thread_id` of the run that produced it. All API keys see all reports (there is no per-user isolation).

### `GET /reports`

| Query | Default | Notes |
|---|---|---|
| `limit` | `20` | 1 to 100 |
| `offset` | `0` | |

Returns an array of summaries, newest first:

```json
[{"id": "a7b311e8...", "question": "What is a modular monolith?", "status": "complete",
  "created_at": "2026-11-17T00:50:12Z", "sources": 6, "warnings": 1}]
```

### `GET /reports/{report_id}`

Returns the full [`Report`](#report), or `404`.

### `DELETE /reports/{report_id}`

Deletes the report and its indexed quotes. Returns `204`, or `404` if it does not exist.

## Memory search

### `GET /memory/search`

Semantic search over the verified quotes from every stored report.

| Query | Default | Notes |
|---|---|---|
| `q` | required | 3 to 500 characters |
| `k` | `5` | 1 to 20 results |
| `min_score` | `0.0` | Cosine similarity threshold, -1 to 1 |

Returns an array of hits, best first:

```json
[{"text": "Hybrid retrieval yields 42 percent higher recall ...", "url": "https://example.com/paper",
  "title": "Hybrid retrieval paper", "published": null, "report_id": "a7b311e8...",
  "score": 0.71, "indexed_at": "2026-11-17T00:50:12Z"}]
```

Score quality depends on the embedder. The offline `hash` embedder only matches shared words; OpenAI, Google or fastembed embeddings match meaning. With `MARS_USE_MEMORY=true` the same index is also used automatically during research.

## Health

### `GET /health`

Unauthenticated.

```json
{"status": "ok", "provider": "google_genai", "search": "ddg", "active_runs": 0,
 "storage": "postgres", "persistent": true}
```

`storage` is `postgres`, `sqlite` or `off`. `persistent` is true when paused runs survive a restart.

## Data models

### Report

| Field | Type | Notes |
|---|---|---|
| `question` | string | The normalized question |
| `status` | string | `complete`, `insufficient_evidence` or `rejected` |
| `markdown` | string | The report. Inline citations look like `[1]`; a `## Sources` section is appended and lists only cited sources |
| `sources` | [`Source`](#source)[] | Cited sources (all sources if none were cited) |
| `insights` | `{text, source_ids}`[] | The analyst's findings behind the report |
| `contradictions` | string[] | Where sources disagree |
| `gaps` | string[] | What the evidence did not cover |
| `citation_check` | object | `cited_ids`, `invalid_ids`, `uncited_paragraphs`, `coverage` (share of sources cited) |
| `critic_approved` | boolean \| null | `false` means the revision budget ran out before the critic approved |
| `drafts` | integer | Number of drafts written |
| `rounds` | integer | Research rounds run (more than 1 means follow-up searches) |
| `dropped_claims` | integer | Claims discarded because their quote was not found in the source text |
| `warnings` | string[] | Quality signals: failed tasks, dropped claims, single-domain evidence, critic not satisfied |
| `errors` | string[] | Per-task failures, as `"<query>: <error>"` |
| `usage` | object | `llm_calls`, `input_tokens`, `output_tokens`, `searches`, `pages_fetched`, `cache_hits` for the run (for a resumed run, only the final leg) |

### Source

| Field | Type | Notes |
|---|---|---|
| `id` | integer | The `n` in `[n]` citations |
| `title`, `url` | string | |
| `snippet` | string | Search snippet (truncated) |
| `published` | string \| null | When the search provider supplied a date |
| `quotes` | string[] | Verbatim excerpts verified against the page text |

## Client examples

### curl (blocking, then approval)

```bash
KEY=your-key
R=$(curl -s -X POST localhost:8000/research -H "X-API-Key: $KEY" -H 'content-type: application/json' \
    -d '{"question": "Microservices vs modular monoliths in 2026", "require_approval": true}')
ID=$(echo "$R" | python3 -c 'import sys,json; print(json.load(sys.stdin)["thread_id"])')

curl -s -X POST "localhost:8000/research/$ID/approve" -H "X-API-Key: $KEY" \
  -H 'content-type: application/json' -d '{"approved": true, "feedback": "focus on team size"}'
```

### Python (streaming)

```python
import json
import httpx

url = "http://localhost:8000/research/stream"
headers = {"X-API-Key": "your-key"}
body = {"question": "Compare the current approaches to RAG evaluation"}

with httpx.stream("POST", url, json=body, headers=headers, timeout=None) as r:
    r.raise_for_status()
    for line in r.iter_lines():
        if line.startswith("data: "):
            ev = json.loads(line[6:])
            if ev["event"] == "step":
                print("step:", ev["node"])
            elif ev["event"] == "report":
                print(ev["report"]["markdown"])
            elif ev["event"] in ("error", "awaiting_approval"):
                print(ev)
```

### JavaScript (browser or Node 18+)

```js
const res = await fetch("http://localhost:8000/research/stream", {
  method: "POST",
  headers: { "content-type": "application/json", "X-API-Key": "your-key" },
  body: JSON.stringify({ question: "Compare the current approaches to RAG evaluation" }),
});
const reader = res.body.getReader();
const decoder = new TextDecoder();
let buffer = "";
for (;;) {
  const { done, value } = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, { stream: true });
  const frames = buffer.split("\n\n");
  buffer = frames.pop(); // keep the incomplete tail
  for (const frame of frames) {
    const data = frame.split("\n").find((l) => l.startsWith("data: "));
    if (data) console.log(JSON.parse(data.slice(6)));
  }
}
```

(`EventSource` cannot be used because it only supports GET and cannot send custom headers.)
