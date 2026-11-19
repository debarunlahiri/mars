"""Keep the document index in step with a folder: add new files, re-index changed ones, drop deleted ones."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel

from ..core.logging import get_logger
from .extract import SUPPORTED

if TYPE_CHECKING:
    from .service import DocumentService

log = get_logger("docs.sync")


class SyncReport(BaseModel):
    started_at: datetime
    finished_at: datetime | None = None
    added: list[str] = []
    updated: list[str] = []
    removed: list[str] = []
    unchanged: int = 0
    duplicates: list[str] = []  # files whose content is already indexed under another name
    failed: dict[str, str] = {}  # path -> reason (retried only after the file changes)
    error: str | None = None  # the whole scan failed (e.g. the folder is missing)

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated or self.removed)


def _scan(root: Path) -> dict[str, tuple[Path, float, int]]:
    """Supported files under ``root`` (no hidden files, Office lock files or symlinks)."""
    found: dict[str, tuple[Path, float, int]] = {}
    for p in root.rglob("*"):
        rel = p.relative_to(root)
        if p.is_symlink() or not p.is_file():
            continue
        if any(part.startswith((".", "~$")) for part in rel.parts) or p.suffix.lower() not in SUPPORTED:
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        found[rel.as_posix()] = (p, st.st_mtime, st.st_size)
    return found


class DocumentSync:
    def __init__(self, docs: DocumentService, folder: str, interval: float = 30.0):
        self.docs = docs
        self.root = Path(folder).expanduser().resolve()
        self.interval = interval
        self.last: SyncReport | None = None
        self._lock = asyncio.Lock()  # one scan at a time (timer, API call and CLI cannot overlap)
        self._task: asyncio.Task | None = None
        self._failed: dict[str, tuple[float, int]] = {}  # path -> (mtime, size) of a failed/duplicate file

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    def status(self) -> dict:
        return {
            "enabled": True,
            "folder": str(self.root),
            "interval_seconds": self.interval,
            "watching": self.running and self.interval > 0,
            "scanning": self._lock.locked(),
            "last": self.last.model_dump(mode="json") if self.last else None,
        }

    # ------------------------------------------------------------------ one pass

    async def sync_once(self) -> SyncReport:
        async with self._lock:
            report = SyncReport(started_at=datetime.now(UTC))
            try:
                await self._pass(report)
            except Exception as exc:  # noqa: BLE001 - a bad pass must never kill the watcher
                log.exception("document sync failed")
                report.error = f"{type(exc).__name__}: {str(exc)[:200]}"
            report.finished_at = datetime.now(UTC)
            self.last = report
            if report.changed or report.failed or report.error:
                log.info(
                    "sync: +%d ~%d -%d (%d failed)",
                    len(report.added), len(report.updated), len(report.removed), len(report.failed),
                )  # fmt: skip
            return report

    async def _pass(self, report: SyncReport) -> None:
        store = self.docs.store
        if not self.root.is_dir():
            report.error = f"folder not found: {self.root}"
            return
        disk = await asyncio.to_thread(_scan, self.root)
        known = await store.synced()

        # Removals first: a renamed file then frees its content hash before the new name is indexed.
        for src, (doc_id, *_rest) in known.items():
            if src not in disk:
                await store.delete(doc_id)
                report.removed.append(src)
        self._failed = {k: v for k, v in self._failed.items() if k in disk}

        for src, (path, mtime, size) in disk.items():
            prev = known.get(src) if src not in report.removed else None
            if prev and prev[1] == mtime and prev[2] == size:
                report.unchanged += 1
                continue
            if self._failed.get(src) == (mtime, size):
                continue  # failed or duplicate before and the file has not changed since
            try:
                data = await asyncio.to_thread(path.read_bytes)
            except OSError as exc:
                report.failed[src] = f"unreadable: {exc.strerror or type(exc).__name__}"
                continue
            if prev and prev[3] == hashlib.sha256(data).hexdigest():  # touched, content identical
                await store.touch(prev[0], mtime)
                report.unchanged += 1
                continue
            res = await self.docs.ingest(path.name, data, source=src, mtime=mtime)
            if res.status == "indexed":
                if prev:
                    await store.delete(prev[0])
                    report.updated.append(src)
                else:
                    report.added.append(src)
                continue
            if prev:  # the old text is stale either way
                await store.delete(prev[0])
                report.removed.append(src)
            self._failed[src] = (mtime, size)
            if res.status == "duplicate":
                report.duplicates.append(src)
            else:
                report.failed[src] = res.error or "failed"

    # ------------------------------------------------------------------ background loop

    def start(self) -> None:
        if self.running:
            return
        self._task = asyncio.create_task(self._loop(), name="mars-docs-sync")

    async def _loop(self) -> None:
        while True:
            await self.sync_once()
            if self.interval <= 0:
                return
            await asyncio.sleep(self.interval)

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._task
            self._task = None
