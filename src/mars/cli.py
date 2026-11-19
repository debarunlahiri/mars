"""Command line: ``mars ask | ingest | sync | docs | serve | eval | doctor``."""

from __future__ import annotations

import argparse
import asyncio
import json
import sys

from .core.config import get_settings
from .core.logging import setup_logging


async def _ask(question: str, approve: bool, as_json: bool, quiet: bool) -> int:
    from .workflow.runtime import open_runtime

    runtime = await open_runtime(get_settings())
    svc = runtime.service
    try:
        events = svc.start(question, require_approval=approve)
        while True:
            resume = None
            async for ev in events:
                kind = ev["event"]
                if kind == "step" and not quiet:
                    extra = {k: v for k, v in ev.items() if k not in ("event", "node")}
                    print(f"[{ev['node']}] {json.dumps(extra, default=str)}", file=sys.stderr)
                elif kind == "awaiting_approval":
                    p = ev["preview"]
                    print("\n--- Awaiting approval ---", file=sys.stderr)
                    for i in p["insights"]:
                        print(f"  * {i['text']} {i['source_ids']}", file=sys.stderr)
                    for g in p["gaps"]:
                        print(f"  ? gap: {g}", file=sys.stderr)
                    ok = input("Approve and write the report? [y/N] ").strip().lower() == "y"
                    fb = input("Guidance for the writer (optional): ").strip() if ok else ""
                    resume = svc.resume(ev["thread_id"], ok, fb)
                elif kind == "report":
                    r = ev["report"]
                    print(json.dumps(r, indent=2) if as_json else r["markdown"])
                    for w in r["warnings"]:
                        print(f"warning: {w}", file=sys.stderr)
                    if ev.get("stored"):
                        print(f"saved as report {ev['thread_id']}", file=sys.stderr)
                    return 0
                elif kind == "error":
                    print(f"error [{ev['code']}]: {ev['detail']}", file=sys.stderr)
                    return 1
            if resume is None:
                return 1
            events = resume
    finally:
        await runtime.aclose()


async def _open_docs():
    from .docs import open_documents

    s = get_settings()
    if not s.docs_db:
        print("documents are not enabled (set MARS_DOCS_DB, e.g. ./mars-docs.db)", file=sys.stderr)
        return None
    from .workflow.deps import build_deps

    deps = build_deps(s)  # the LLM doubles as the image reader
    docs = await open_documents(s, getattr(deps.fast, "describe_image", None))
    return docs, deps


async def _ingest(paths: list[str]) -> int:
    from pathlib import Path

    from .docs import SUPPORTED

    opened = await _open_docs()
    if opened is None:
        return 1
    docs, deps = opened
    files: list[Path] = []
    for raw in paths:
        p = Path(raw).expanduser()
        if p.is_dir():
            files += sorted(f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in SUPPORTED)
        else:
            files.append(p)
    failed = 0
    try:
        print(f"embeddings: {docs.describe()['embeddings']} on {docs.describe()['device']}", file=sys.stderr)
        for f in files:
            if not f.is_file():
                print(f"missing   {f}")
                failed += 1
                continue
            r = await docs.ingest(f.name, f.read_bytes())
            detail = f"{r.document.chunks} passages" if r.document else r.error
            print(f"{r.status:<9} {f}  ({detail})")
            failed += r.status == "failed"
    finally:
        await deps.aclose()
        await docs.aclose()
    return 1 if failed else 0


async def _sync() -> int:
    opened = await _open_docs()
    if opened is None:
        return 1
    docs, deps = opened
    try:
        if docs.sync is None:
            print("no folder to sync (set MARS_DOCS_DIR)", file=sys.stderr)
            return 1
        r = await docs.sync.sync_once()
        print(
            f"added {len(r.added)}, updated {len(r.updated)}, removed {len(r.removed)}, "
            f"unchanged {r.unchanged}, failed {len(r.failed)}"
        )
        for path, why in r.failed.items():
            print(f"  failed {path}: {why}")
        if r.error:
            print(f"error: {r.error}", file=sys.stderr)
        return 1 if r.error or r.failed else 0
    finally:
        await deps.aclose()
        await docs.aclose()


async def _docs_list(delete: str | None) -> int:
    opened = await _open_docs()
    if opened is None:
        return 1
    docs, deps = opened
    try:
        if delete:
            ok = await docs.delete(delete)
            print("deleted" if ok else "not found")
            return 0 if ok else 1
        for d in await docs.list():
            print(f"{d.id}  {d.kind:<5} {d.chunks:>4} passages  {d.name}")
    finally:
        await deps.aclose()
        await docs.aclose()
    return 0


async def _reports(limit: int) -> int:
    from .storage import open_storage

    store = await open_storage(get_settings())
    if store is None:
        print("storage is not configured (set MARS_DATABASE_URL or MARS_STORAGE_DB)", file=sys.stderr)
        return 1
    try:
        for r in await store.list_reports(limit):
            print(f"{r.id}  {r.created_at:%Y-%m-%d %H:%M}  {r.status:<9} {r.sources:>2} src  {r.question}")
    finally:
        await store.aclose()
    return 0


async def _memory(query: str, k: int) -> int:
    from .storage import open_storage

    store = await open_storage(get_settings())
    if store is None:
        print("storage is not configured (set MARS_DATABASE_URL or MARS_STORAGE_DB)", file=sys.stderr)
        return 1
    try:
        for h in await store.search(query, k):
            print(f"{h.score:.2f}  {h.url}\n      {h.text[:160]}")
    finally:
        await store.aclose()
    return 0


async def _eval(dataset: str | None) -> int:
    from .evaluation import evaluate, load_cases
    from .workflow.deps import build_deps
    from .workflow.graph import build_graph

    deps = build_deps(get_settings())
    graph = build_graph(deps)
    results = []
    try:
        for i, case in enumerate(load_cases(dataset)):
            out = await graph.ainvoke(
                {"question": case.question, "findings": []},
                {"configurable": {"thread_id": f"eval-{i}"}},
            )
            res = await evaluate(out["report"], deps, case.expected_topics)
            results.append({"question": case.question, **res.to_dict()})
    finally:
        await deps.aclose()
    print(json.dumps(results, indent=2))
    return 0 if all(r["passed"] for r in results) else 1


async def _doctor() -> int:
    """Verify configuration against the real services before a long run."""
    from .workflow.deps import build_deps

    s = get_settings()
    fast, strong = s.models()
    print(f"provider={s.resolved_provider()} models={fast}/{strong} search={s.resolved_search()}")
    print(
        f"fetch_pages={s.fetch_pages} auth={'on' if s.api_key_list else 'OFF'} "
        f"persistent={'yes' if s.checkpoint_db else 'no (in-memory)'}"
    )
    from .docs import available_devices, resolve_device

    print(
        f"device={resolve_device(s.device)} (available: {', '.join(available_devices())}) "
        f"documents={'on' if s.docs_db else 'off'} web_search={s.web_search}"
    )
    deps = build_deps(s)
    ok = True
    try:
        try:
            results = await deps.search.search("python programming language", 3)
            print(f"search: OK ({len(results)} results)")
            ok &= bool(results)
            if deps.fetcher and results:
                text = await deps.fetcher.fetch(results[0].url)
                print(f"fetch:  {'OK' if text else 'no text extracted'} ({results[0].url})")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"search: FAILED {type(exc).__name__}: {exc}")
        try:
            reply = await deps.fast.text("Reply with the single word OK.", "ping")
            print(f"llm:    OK ({reply[:30]!r})")
        except Exception as exc:  # noqa: BLE001
            ok = False
            print(f"llm:    FAILED {type(exc).__name__}: {exc}")
    finally:
        await deps.aclose()
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="mars", description="Multi-Agent Research System")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("ask", help="research a question and print the report")
    a.add_argument("question")
    a.add_argument("--approve", action="store_true", help="pause for human approval")
    a.add_argument("--json", action="store_true", help="print the full report as JSON")
    a.add_argument("--quiet", action="store_true", help="hide progress on stderr")

    s = sub.add_parser("serve", help="run the FastAPI server")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)

    e = sub.add_parser("eval", help="run the evaluation on a dataset")
    e.add_argument("--dataset", help="JSON file: list of questions or {question, expected_topics}")

    r = sub.add_parser("reports", help="list stored reports")
    r.add_argument("--limit", type=int, default=20)

    m = sub.add_parser("memory", help="semantic search over stored, verified quotes")
    m.add_argument("query")
    m.add_argument("-k", type=int, default=5)

    i = sub.add_parser("ingest", help="index files/folders (PDF, Word, PowerPoint, Excel, images, text)")
    i.add_argument("paths", nargs="+")

    sub.add_parser("sync", help="bring the index in line with MARS_DOCS_DIR once")

    d = sub.add_parser("docs", help="list indexed documents")
    d.add_argument("--delete", metavar="ID", help="remove a document from the index")

    sub.add_parser("doctor", help="check keys, search, page fetching and the LLM")

    args = p.parse_args(argv)
    cfg = get_settings()
    setup_logging("WARNING" if args.cmd == "ask" else cfg.log_level, cfg.log_json)
    if args.cmd == "serve":
        import uvicorn

        uvicorn.run("mars.api.app:get_app", factory=True, host=args.host, port=args.port)
    elif args.cmd == "ask":
        sys.exit(asyncio.run(_ask(args.question, args.approve, args.json, args.quiet)))
    elif args.cmd == "ingest":
        sys.exit(asyncio.run(_ingest(args.paths)))
    elif args.cmd == "sync":
        sys.exit(asyncio.run(_sync()))
    elif args.cmd == "docs":
        sys.exit(asyncio.run(_docs_list(args.delete)))
    elif args.cmd == "reports":
        sys.exit(asyncio.run(_reports(args.limit)))
    elif args.cmd == "memory":
        sys.exit(asyncio.run(_memory(args.query, args.k)))
    elif args.cmd == "eval":
        sys.exit(asyncio.run(_eval(args.dataset)))
    else:
        sys.exit(asyncio.run(_doctor()))


if __name__ == "__main__":
    main()
