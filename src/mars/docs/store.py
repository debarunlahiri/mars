"""SQLite index of internal documents: metadata + embedded passages (exact cosine search)."""

from __future__ import annotations

from datetime import UTC, datetime

import aiosqlite
import numpy as np
from pydantic import BaseModel

from ..storage.base import StorageError
from ..storage.embeddings import Embedder
from .chunk import DocChunk

SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, kind TEXT NOT NULL, sha256 TEXT NOT NULL UNIQUE,
  size INTEGER NOT NULL, chunks INTEGER NOT NULL, created_at TEXT NOT NULL, notes TEXT NOT NULL DEFAULT '',
  source TEXT, mtime REAL);
CREATE TABLE IF NOT EXISTS doc_chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  pos INTEGER NOT NULL, label TEXT NOT NULL, text TEXT NOT NULL, embedding BLOB NOT NULL);
CREATE INDEX IF NOT EXISTS doc_chunks_doc ON doc_chunks(doc_id);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class DocumentInfo(BaseModel):
    id: str
    name: str
    kind: str
    size: int
    chunks: int
    created_at: datetime
    notes: list[str] = []
    source: str | None = None  # path (relative to MARS_DOCS_DIR) when kept in sync from a folder


class DocHit(BaseModel):
    doc_id: str
    name: str
    label: str
    text: str
    score: float


class DocumentStore:
    def __init__(self, path: str, embedder: Embedder):
        self.path, self.embedder = path, embedder
        self._db: aiosqlite.Connection | None = None
        self._matrix: np.ndarray | None = None  # all passage vectors; rebuilt after any change
        self._rows: list[tuple[str, str, str, str]] = []  # (doc_id, name, label, text) per matrix row

    async def setup(self) -> None:
        self._db = await aiosqlite.connect(self.path)
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(SCHEMA)
        await self._migrate()
        spec = f"{self.embedder.name}:{self.embedder.dim}"
        async with self._db.execute("SELECT value FROM meta WHERE key='embedding'") as cur:
            row = await cur.fetchone()
        if row and row[0] != spec:
            raise StorageError(
                f"{self.path} was indexed with embeddings '{row[0]}' but '{spec}' is configured. "
                "Use a new MARS_DOCS_DB file or switch back."
            )
        await self._db.execute("INSERT OR REPLACE INTO meta VALUES ('embedding', ?)", (spec,))
        await self._db.commit()

    async def _migrate(self) -> None:
        """Bring an index created by an older version up to the current schema."""
        async with self.db.execute("PRAGMA table_info(documents)") as cur:
            have = {r[1] for r in await cur.fetchall()}
        for col, ddl in (("source", "TEXT"), ("mtime", "REAL")):
            if col not in have:
                await self.db.execute(f"ALTER TABLE documents ADD COLUMN {col} {ddl}")
        await self.db.execute("CREATE INDEX IF NOT EXISTS documents_source ON documents(source)")

    async def aclose(self) -> None:
        if self._db:
            await self._db.close()

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise StorageError("document store not set up")
        return self._db

    @staticmethod
    def _info(row) -> DocumentInfo:
        id_, name, kind, size, chunks, created, notes, source = row
        return DocumentInfo(
            id=id_, name=name, kind=kind, size=size, chunks=chunks, source=source,
            created_at=datetime.fromisoformat(created), notes=[n for n in notes.split("\n") if n],
        )  # fmt: skip

    _COLS = "id, name, kind, size, chunks, created_at, notes, source"

    async def find_by_hash(self, sha256: str) -> DocumentInfo | None:
        async with self.db.execute(f"SELECT {self._COLS} FROM documents WHERE sha256=?", (sha256,)) as cur:
            row = await cur.fetchone()
        return self._info(row) if row else None

    async def add(
        self, doc_id: str, name: str, kind: str, sha256: str, size: int, notes: list[str],
        chunks: list[DocChunk], vectors: np.ndarray, source: str | None = None, mtime: float | None = None,
    ) -> DocumentInfo:  # fmt: skip
        now = datetime.now(UTC).isoformat()
        await self.db.execute(
            "INSERT INTO documents (id,name,kind,sha256,size,chunks,created_at,notes,source,mtime) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (doc_id, name, kind, sha256, size, len(chunks), now, "\n".join(notes), source, mtime),
        )
        await self.db.executemany(
            "INSERT INTO doc_chunks (doc_id,pos,label,text,embedding) VALUES (?,?,?,?,?)",
            [
                (doc_id, c.pos, c.label, c.text, np.asarray(v, np.float32).tobytes())
                for c, v in zip(chunks, vectors, strict=True)
            ],
        )
        await self.db.commit()
        self._matrix = None
        return DocumentInfo(
            id=doc_id, name=name, kind=kind, size=size, chunks=len(chunks),
            created_at=datetime.fromisoformat(now), notes=notes, source=source,
        )  # fmt: skip

    async def synced(self) -> dict[str, tuple[str, float | None, int, str]]:
        """Folder-synced documents: source path -> (doc id, mtime, size, sha256)."""
        async with self.db.execute(
            "SELECT source, id, mtime, size, sha256 FROM documents WHERE source IS NOT NULL"
        ) as cur:
            return {r[0]: (r[1], r[2], r[3], r[4]) for r in await cur.fetchall()}

    async def touch(self, doc_id: str, mtime: float) -> None:
        await self.db.execute("UPDATE documents SET mtime=? WHERE id=?", (mtime, doc_id))
        await self.db.commit()

    async def list_all(self) -> list[DocumentInfo]:
        async with self.db.execute(f"SELECT {self._COLS} FROM documents ORDER BY created_at DESC") as cur:
            return [self._info(r) for r in await cur.fetchall()]

    async def get(self, doc_id: str) -> DocumentInfo | None:
        async with self.db.execute(f"SELECT {self._COLS} FROM documents WHERE id=?", (doc_id,)) as cur:
            row = await cur.fetchone()
        return self._info(row) if row else None

    async def delete(self, doc_id: str) -> bool:
        cur = await self.db.execute("DELETE FROM documents WHERE id=?", (doc_id,))
        await self.db.commit()
        self._matrix = None
        return cur.rowcount > 0

    async def count(self) -> int:
        async with self.db.execute("SELECT COUNT(*) FROM documents") as cur:
            return int((await cur.fetchone())[0])  # type: ignore[index]

    async def _load(self) -> None:
        async with self.db.execute(
            "SELECT c.doc_id, d.name, c.label, c.text, c.embedding FROM doc_chunks c "
            "JOIN documents d ON d.id = c.doc_id ORDER BY c.id"
        ) as cur:
            rows = await cur.fetchall()
        self._rows = [(r[0], r[1], r[2], r[3]) for r in rows]
        dim = self.embedder.dim
        self._matrix = (
            np.vstack([np.frombuffer(r[4], dtype=np.float32) for r in rows])
            if rows
            else np.zeros((0, dim), dtype=np.float32)
        )

    async def intro(self, doc_ids: list[str], chars: int = 500) -> list[tuple[str, str]]:
        """(name, opening text) for each document, in the order given."""
        out = []
        for doc_id in doc_ids:
            async with self.db.execute(
                "SELECT d.name, c.text FROM documents d JOIN doc_chunks c ON c.doc_id=d.id "
                "WHERE d.id=? ORDER BY c.pos LIMIT 1",
                (doc_id,),
            ) as cur:
                row = await cur.fetchone()
            if row:
                out.append((row[0], row[1][:chars]))
        return out

    async def search(
        self, query: str, k: int = 8, min_score: float = 0.0, doc_ids: list[str] | None = None
    ) -> list[DocHit]:
        if self._matrix is None:
            await self._load()
        assert self._matrix is not None
        if not len(self._rows):
            return []
        q = (await self.embedder.embed([query]))[0]
        scores = self._matrix @ q
        if doc_ids is not None:  # restrict to specific documents
            allowed = set(doc_ids)
            scores = np.where([r[0] in allowed for r in self._rows], scores, -np.inf)
        order = np.argsort(-scores)[:k]
        return [
            DocHit(doc_id=d, name=n, label=lab, text=t, score=float(scores[i]))
            for i in order
            for d, n, lab, t in [self._rows[i]]
            if scores[i] >= min_score and np.isfinite(scores[i])
        ]
