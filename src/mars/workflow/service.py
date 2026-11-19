"""Runs the graph and turns LangGraph updates into a simple event stream (used by API + CLI)."""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import AsyncIterator
from typing import Any

from langgraph.types import Command

from ..core.config import Settings, get_settings
from ..core.errors import MarsError, RunTimeout
from ..core.logging import get_logger, run_id_var
from ..core.text import clean_text
from ..core.usage import Usage, usage_var
from ..schemas import Report
from .deps import Deps, build_deps
from .graph import build_graph

log = get_logger("service")


def describe(node: str, update: dict[str, Any]) -> dict[str, Any]:
    """Compact, JSON-safe summary of one node's state update."""
    if node == "planner":
        return {"tasks": [t.query for t in update["plan"]]}
    if node == "researcher":
        f = update["findings"][0]
        return {
            "task": f.task.query,
            "sources": len(f.sources),
            "pages_read": f.pages_fetched,
            "claims": len(f.key_points),
            "dropped": f.dropped_claims,
            "error": f.error,
        }
    if node == "analyst":
        return {
            "insights": len(update["analysis"].insights),
            "sources": len(update["sources"]),
            "followups": [t.query for t in update["followups"]],
        }
    if node == "approval":
        return {"approved": update["approved"]}
    if node == "writer":
        return {"draft": update["drafts"]}
    if node == "critic":
        return {"approved": update["critique"].approved, "issues": update["critique"].issues}
    if node == "finalize":
        return {"status": update["report"].status}
    return {}


class ResearchService:
    def __init__(
        self,
        settings: Settings | None = None,
        graph=None,
        deps: Deps | None = None,
        checkpointer=None,
        storage=None,
    ):
        self.settings = settings or get_settings()
        self.deps = deps or build_deps(self.settings)
        if storage is not None:
            self.deps.storage = storage
        self.graph = graph or build_graph(self.deps, checkpointer)
        self.active = 0  # runs currently streaming (for load shedding)

    async def aclose(self) -> None:
        await self.deps.aclose()

    @staticmethod
    def normalize_question(question: str) -> str:
        return clean_text(question).replace("\n", " ")

    async def start(
        self,
        question: str,
        require_approval: bool = False,
        thread_id: str | None = None,
        document_ids: list[str] | None = None,
        web_search: bool | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        """``document_ids``: files attached to the question. They are read first and, unless
        ``web_search`` is true, are the only evidence (so "explain this" explains the file)."""
        thread_id = thread_id or uuid.uuid4().hex
        question = self.normalize_question(question)
        payload: dict[str, Any] = {"require_approval": require_approval, "findings": []}
        if document_ids and self.deps.docs is not None:
            attached = await self.deps.docs.existing(document_ids)
            if attached:
                names = ", ".join(d.name for d in attached)
                question = f"{question} (about the attached document{'s' if len(attached) > 1 else ''}: {names})"
                payload["scope"] = {
                    "document_ids": [d.id for d in attached],
                    "web": bool(web_search) if web_search is not None else False,
                }
        elif web_search is not None:
            payload["scope"] = {"document_ids": [], "web": web_search}
        payload["question"] = question
        async for ev in self._stream(payload, thread_id):
            yield ev

    async def resume(
        self, thread_id: str, approved: bool, feedback: str = ""
    ) -> AsyncIterator[dict[str, Any]]:
        cmd = Command(resume={"approved": approved, "feedback": clean_text(feedback, 2000)})
        async for ev in self._stream(cmd, thread_id):
            yield ev

    async def _persist(self, report_id: str, report: Report) -> bool:
        """Save finished reports + index their verified quotes. Never fails the run."""
        if self.deps.storage is None or report.status != "complete":
            return False
        try:
            await self.deps.storage.save_report(report_id, report)
            return True
        except Exception:  # noqa: BLE001
            log.exception("could not store report %s (run result is still returned)", report_id)
            return False

    async def is_waiting(self, thread_id: str) -> bool:
        state = await self.graph.aget_state({"configurable": {"thread_id": thread_id}})
        return bool(state.next)

    async def _stream(self, graph_input: Any, thread_id: str) -> AsyncIterator[dict[str, Any]]:
        config = {"configurable": {"thread_id": thread_id}}
        run_token = run_id_var.set(thread_id[:8])
        usage_token = usage_var.set(Usage())
        self.active += 1
        started = time.monotonic()
        deadline = started + self.settings.run_timeout
        stream = None
        yield {"event": "started", "thread_id": thread_id}
        try:
            stream = self.graph.astream(graph_input, config, stream_mode="updates").__aiter__()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise RunTimeout(f"run exceeded {self.settings.run_timeout:.0f}s")
                try:
                    chunk = await asyncio.wait_for(stream.__anext__(), remaining)
                except StopAsyncIteration:
                    break
                except TimeoutError as exc:
                    raise RunTimeout(f"run exceeded {self.settings.run_timeout:.0f}s") from exc
                for node, update in chunk.items():
                    if node == "__interrupt__":
                        yield {
                            "event": "awaiting_approval",
                            "thread_id": thread_id,
                            "preview": update[0].value,
                        }
                        return
                    if update:
                        yield {"event": "step", "node": node, **describe(node, update)}
            state = await self.graph.aget_state(config)
            report: Report = state.values["report"]
            log.info(
                "done status=%s in %.1fs usage=%s",
                report.status,
                time.monotonic() - started,
                report.usage,
            )
            stored = await self._persist(thread_id, report)
            yield {
                "event": "report",
                "thread_id": thread_id,
                "report": report.model_dump(),
                "stored": stored,
            }
        except MarsError as exc:
            log.warning("run failed: %s", exc)
            yield {
                "event": "error",
                "thread_id": thread_id,
                "code": exc.code,
                "status": exc.status_code,
                "detail": str(exc),
            }
        except Exception:  # noqa: BLE001
            error_id = uuid.uuid4().hex[:8]
            log.exception("run crashed (error_id=%s)", error_id)
            # Internals stay in the log; the client gets an id to quote.
            yield {
                "event": "error",
                "thread_id": thread_id,
                "code": "internal_error",
                "status": 500,
                "detail": f"Research failed unexpectedly (error_id={error_id}).",
            }
        finally:
            self.active -= 1
            if stream is not None:
                with contextlib.suppress(Exception):
                    await stream.aclose()
            with contextlib.suppress(ValueError):  # token from another context (client disconnect)
                usage_var.reset(usage_token)
                run_id_var.reset(run_token)


async def run_to_completion(events: AsyncIterator[dict]) -> dict:
    """Consume a stream and return its last event (report, awaiting_approval or error)."""
    last: dict = {}
    async for ev in events:
        last = ev
    return last
