"""Ingest files into the document index and retrieve passages as research evidence."""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass
from urllib.parse import quote

import numpy as np

from ..core.config import Settings
from ..core.logging import get_logger
from ..schemas import SearchResult
from ..storage.embeddings import Embedder, build_embedder
from .chunk import chunk_segments
from .device import describe_device, resolve_device
from .extract import ExtractionError, Vision, extract
from .sync import DocumentSync
from .store import DocHit, DocumentInfo, DocumentStore

log = get_logger("docs")

DOC_SCHEME = "doc://"
MAX_EXTRACTED_CHARS = 2_000_000
EMBED_BATCH = 64


@dataclass
class IngestResult:
    name: str
    status: str  # indexed | duplicate | failed
    document: DocumentInfo | None = None
    error: str | None = None


def is_doc_url(url: str) -> bool:
    return url.startswith(DOC_SCHEME)


def _slug(name: str) -> str:
    return quote(re.sub(r"\s+", "_", name.strip()) or "file", safe="._-")


class DocumentService:
    def __init__(self, settings: Settings, store: DocumentStore, vision: Vision | None = None):
        self.settings, self.store, self.vision = settings, store, vision
        self.device = resolve_device(settings.device)
        self.sync: DocumentSync | None = None  # set by open_documents when MARS_DOCS_DIR is configured

    @property
    def embedder(self) -> Embedder:
        return self.store.embedder

    def describe(self) -> dict:
        return {
            "embeddings": self.embedder.name,
            "device": describe_device(getattr(self.embedder, "device", None) or self.device),
            "vision": self.vision is not None,
        }

    async def aclose(self) -> None:
        if self.sync:
            await self.sync.stop()
        await self.store.aclose()

    # -------------------------------------------------------------- ingest

    async def ingest(
        self, name: str, data: bytes, source: str | None = None, mtime: float | None = None
    ) -> IngestResult:
        """Index one file. Never raises for a bad file: the failure is reported in the result."""
        name = (name or "file").replace("\\", "/").rsplit("/", 1)[-1][:200]
        limit = self.settings.max_upload_mb * 1024 * 1024
        if len(data) > limit:
            return IngestResult(name, "failed", error=f"file exceeds {self.settings.max_upload_mb} MB")
        if not data:
            return IngestResult(name, "failed", error="file is empty")
        sha = hashlib.sha256(data).hexdigest()
        if existing := await self.store.find_by_hash(sha):
            return IngestResult(name, "duplicate", existing)
        try:
            extracted = await extract(name, data, self.vision if self.settings.vision_images else None)
            if extracted.chars > MAX_EXTRACTED_CHARS:
                extracted.notes.append(f"text truncated to {MAX_EXTRACTED_CHARS:,} characters")
                budget = MAX_EXTRACTED_CHARS
                for seg in extracted.segments:
                    seg.text, budget = seg.text[: max(budget, 0)], budget - len(seg.text)
            chunks = chunk_segments(extracted.segments, self.settings.chunk_chars, self.settings.chunk_overlap)
            if not chunks:
                raise ExtractionError("no readable text found in the file")
            vectors = []
            for i in range(0, len(chunks), EMBED_BATCH):
                vectors.append(await self.embedder.embed([c.text for c in chunks[i : i + EMBED_BATCH]]))
            info = await self.store.add(
                uuid.uuid4().hex[:12], name, extracted.kind, sha, len(data), extracted.notes,
                chunks, np.vstack(vectors), source, mtime,
            )  # fmt: skip
        except ExtractionError as exc:
            return IngestResult(name, "failed", error=str(exc))
        except Exception as exc:  # noqa: BLE001 - one bad file must not break a batch upload
            log.exception("could not ingest %s", name)
            return IngestResult(name, "failed", error=f"{type(exc).__name__}: {str(exc)[:150]}")
        log.info("indexed %s: %s, %d passages", name, info.kind, info.chunks)
        return IngestResult(name, "indexed", info)

    # -------------------------------------------------------------- retrieve

    async def list(self) -> list[DocumentInfo]:
        return await self.store.list_all()

    async def delete(self, doc_id: str) -> bool:
        return await self.store.delete(doc_id)

    async def count(self) -> int:
        return await self.store.count()

    async def search(
        self, query: str, k: int = 8, min_score: float | None = None, doc_ids: list[str] | None = None
    ) -> list[DocHit]:
        score = self.settings.docs_min_score if min_score is None else min_score
        return await self.store.search(query, k, score, doc_ids)

    async def existing(self, doc_ids: list[str]) -> list[DocumentInfo]:
        """The requested documents that are indexed (unknown ids are dropped), in order."""
        found = [d for i in dict.fromkeys(doc_ids) if (d := await self.store.get(i))]
        return found

    async def outline(self, doc_ids: list[str]) -> str:
        """Names and opening text of attached documents, so the planner knows what "this" is."""
        return "\n".join(f"- {n}: {t!r}" for n, t in await self.store.intro(doc_ids))

    async def evidence(self, query: str, doc_ids: list[str] | None = None) -> list[SearchResult]:
        """Best passages for ``query``, grouped into one citable source per document.

        With ``doc_ids`` (files the user attached to the question) only those documents are searched
        and no similarity threshold applies: the user pointed at them, so the closest passages are used.
        """
        s = self.settings
        if doc_ids:
            hits = await self.search(query, k=max(s.docs_top_k * 3, 8) * len(doc_ids), min_score=-1.0, doc_ids=doc_ids)
        else:
            hits = await self.search(query, k=s.docs_top_k * 3)
        grouped: dict[str, list[DocHit]] = {}
        for h in hits:
            grouped.setdefault(h.doc_id, []).append(h)
        out: list[SearchResult] = []
        for doc_id, group in list(grouped.items())[: max(s.docs_top_k, len(doc_ids or []))]:
            body = "\n\n".join(f"[{h.label}] {h.text}" if h.label else h.text for h in group)
            out.append(
                SearchResult(
                    title=f"{group[0].name} (internal document)",
                    url=f"{DOC_SCHEME}{doc_id}/{_slug(group[0].name)}",
                    snippet=group[0].text[:300],
                    content=body,
                    score=group[0].score,
                )
            )
        return out


async def open_documents(s: Settings, vision: Vision | None = None) -> DocumentService | None:
    """Open the document index if ``MARS_DOCS_DB`` is set."""
    if not s.docs_db:
        return None
    store = DocumentStore(s.docs_db, build_embedder(s))
    await store.setup()
    svc = DocumentService(s, store, vision)
    if s.docs_dir:
        svc.sync = DocumentSync(svc, s.docs_dir, s.docs_sync_interval)
    log.info("documents ready: %s", svc.describe())
    return svc
