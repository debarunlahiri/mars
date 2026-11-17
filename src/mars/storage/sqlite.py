"""Single-file storage (reports + vectors) for local use. Search is exact, brute-force cosine."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import aiosqlite
import numpy as np

from ..schemas import Report
from .base import StorageError, chunks_from_report
from .embeddings import Embedder
from .models import ChunkHit, ReportSummary

SCHEMA = """
CREATE TABLE IF NOT EXISTS reports (
  id TEXT PRIMARY KEY, question TEXT NOT NULL, status TEXT NOT NULL,
  created_at TEXT NOT NULL, body TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS chunks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  report_id TEXT NOT NULL REFERENCES reports(id) ON DELETE CASCADE,
  text TEXT NOT NULL, url TEXT NOT NULL, title TEXT NOT NULL, published TEXT,
  embedding BLOB NOT NULL, created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS chunks_report ON chunks(report_id);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""


class SqliteStorage:
    def __init__(self, path: str, embedder: Embedder):
        self.path, self.embedder = path, embedder
        self._db: aiosqlite.Connection | None = None

    async def setup(self) -> None:
        self._db = await aiosqlite.connect(self.path)
        await self._db.execute("PRAGMA foreign_keys=ON")
        await self._db.executescript(SCHEMA)
        spec = f"{self.embedder.name}:{self.embedder.dim}"
        async with self._db.execute("SELECT value FROM meta WHERE key='embedding'") as cur:
            row = await cur.fetchone()
        if row and row[0] != spec:
            raise StorageError(
                f"{self.path} was indexed with embeddings '{row[0]}' but '{spec}' is configured. "
                "Use a new database file or switch back."
            )
        await self._db.execute("INSERT OR REPLACE INTO meta VALUES ('embedding', ?)", (spec,))
        await self._db.commit()

    async def aclose(self) -> None:
        if self._db:
            await self._db.close()

    @property
    def db(self) -> aiosqlite.Connection:
        if self._db is None:
            raise StorageError("storage not set up")
        return self._db

    async def save_report(self, report_id: str, report: Report) -> None:
        chunks = chunks_from_report(report)
        vectors = await self.embedder.embed([c.text for c in chunks]) if chunks else []
        now = datetime.now(UTC).isoformat()
        await self.db.execute("DELETE FROM reports WHERE id=?", (report_id,))  # cascades to chunks
        await self.db.execute(
            "INSERT INTO reports VALUES (?,?,?,?,?)",
            (report_id, report.question, report.status, now, report.model_dump_json()),
        )
        await self.db.executemany(
            "INSERT INTO chunks (report_id,text,url,title,published,embedding,created_at) "
            "VALUES (?,?,?,?,?,?,?)",
            [
                (report_id, c.text, c.url, c.title, c.published, np.asarray(v, np.float32).tobytes(), now)
                for c, v in zip(chunks, vectors, strict=True)
            ],
        )
        await self.db.commit()

    async def get_report(self, report_id: str) -> Report | None:
        async with self.db.execute("SELECT body FROM reports WHERE id=?", (report_id,)) as cur:
            row = await cur.fetchone()
        return Report.model_validate(json.loads(row[0])) if row else None

    async def list_reports(self, limit: int = 20, offset: int = 0) -> list[ReportSummary]:
        async with self.db.execute(
            "SELECT id, question, status, created_at, body FROM reports "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ) as cur:
            rows = await cur.fetchall()
        out = []
        for id_, question, status, created, body in rows:
            r = json.loads(body)
            out.append(
                ReportSummary(
                    id=id_,
                    question=question,
                    status=status,
                    created_at=datetime.fromisoformat(created),
                    sources=len(r.get("sources", [])),
                    warnings=len(r.get("warnings", [])),
                )
            )
        return out

    async def delete_report(self, report_id: str) -> bool:
        cur = await self.db.execute("DELETE FROM reports WHERE id=?", (report_id,))
        await self.db.commit()
        return cur.rowcount > 0

    async def search(self, query: str, k: int = 5, min_score: float = 0.0) -> list[ChunkHit]:
        async with self.db.execute(
            "SELECT report_id,text,url,title,published,embedding,created_at FROM chunks"
        ) as cur:
            rows = await cur.fetchall()
        if not rows:
            return []
        q = (await self.embedder.embed([query]))[0]
        mat = np.vstack([np.frombuffer(r[5], dtype=np.float32) for r in rows])
        scores = mat @ q  # vectors are unit length, so dot product == cosine similarity
        order = np.argsort(-scores)[:k]
        return [
            ChunkHit(
                report_id=rows[i][0],
                text=rows[i][1],
                url=rows[i][2],
                title=rows[i][3],
                published=rows[i][4],
                score=float(scores[i]),
                indexed_at=datetime.fromisoformat(rows[i][6]),
            )
            for i in order
            if scores[i] >= min_score
        ]
