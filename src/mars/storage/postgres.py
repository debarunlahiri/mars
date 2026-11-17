"""PostgreSQL storage; vectors live in pgvector (HNSW cosine index)."""

from __future__ import annotations

import numpy as np
import psycopg
from pgvector.psycopg import register_vector_async
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

from ..core.logging import get_logger
from ..schemas import Report
from .base import StorageError, chunks_from_report
from .embeddings import Embedder
from .models import ChunkHit, ReportSummary

log = get_logger("storage")


class PostgresStorage:
    def __init__(self, url: str, embedder: Embedder, pool_size: int = 5):
        self.url, self.embedder, self.pool_size = url, embedder, pool_size
        self._pool: AsyncConnectionPool | None = None

    async def setup(self) -> None:
        dim = int(self.embedder.dim)
        spec = f"{self.embedder.name}:{dim}"
        # DDL on a plain connection first: pgvector types must exist before the pool registers them.
        async with await psycopg.AsyncConnection.connect(self.url, autocommit=True) as conn:
            try:
                await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            except psycopg.Error as exc:
                raise StorageError(
                    "pgvector is not available. Use an image with it (e.g. pgvector/pgvector:pg16) "
                    f"or have an admin run CREATE EXTENSION vector: {exc}"
                ) from exc
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS mars_meta (key text PRIMARY KEY, value text NOT NULL)"
            )
            row = await (await conn.execute("SELECT value FROM mars_meta WHERE key='embedding'")).fetchone()
            if row and row[0] != spec:
                raise StorageError(
                    f"database was indexed with embeddings '{row[0]}' but '{spec}' is configured. "
                    "Switch back, or use a different database/schema."
                )
            await conn.execute(
                "INSERT INTO mars_meta VALUES ('embedding', %s) ON CONFLICT (key) DO NOTHING", (spec,)
            )
            await conn.execute(
                """CREATE TABLE IF NOT EXISTS mars_reports (
                     id text PRIMARY KEY, question text NOT NULL, status text NOT NULL,
                     created_at timestamptz NOT NULL DEFAULT now(), body jsonb NOT NULL)"""
            )
            await conn.execute(
                f"""CREATE TABLE IF NOT EXISTS mars_chunks (
                      id bigserial PRIMARY KEY,
                      report_id text NOT NULL REFERENCES mars_reports(id) ON DELETE CASCADE,
                      text text NOT NULL, url text NOT NULL, title text NOT NULL, published text,
                      embedding vector({dim}) NOT NULL,
                      created_at timestamptz NOT NULL DEFAULT now())"""
            )
            await conn.execute(
                "CREATE INDEX IF NOT EXISTS mars_reports_created ON mars_reports (created_at DESC)"
            )
            try:  # HNSW supports up to 2000 dims; beyond that fall back to exact search
                await conn.execute(
                    "CREATE INDEX IF NOT EXISTS mars_chunks_embedding "
                    "ON mars_chunks USING hnsw (embedding vector_cosine_ops)"
                )
            except psycopg.Error as exc:
                log.warning("no vector index (searches stay exact but slower): %s", exc)

        self._pool = AsyncConnectionPool(
            self.url, min_size=1, max_size=self.pool_size, open=False, configure=register_vector_async
        )
        await self._pool.open(wait=True, timeout=15)

    async def aclose(self) -> None:
        if self._pool:
            await self._pool.close()

    @property
    def pool(self) -> AsyncConnectionPool:
        if self._pool is None:
            raise StorageError("storage not set up")
        return self._pool

    async def save_report(self, report_id: str, report: Report) -> None:
        chunks = chunks_from_report(report)
        vectors = await self.embedder.embed([c.text for c in chunks]) if chunks else []
        async with self.pool.connection() as conn, conn.transaction():
            await conn.execute("DELETE FROM mars_reports WHERE id=%s", (report_id,))
            await conn.execute(
                "INSERT INTO mars_reports (id, question, status, body) VALUES (%s,%s,%s,%s)",
                (report_id, report.question, report.status, Jsonb(report.model_dump(mode="json"))),
            )
            if chunks:
                async with conn.cursor() as cur:
                    await cur.executemany(
                        "INSERT INTO mars_chunks (report_id,text,url,title,published,embedding) "
                        "VALUES (%s,%s,%s,%s,%s,%s)",
                        [
                            (report_id, c.text, c.url, c.title, c.published, np.asarray(v, np.float32))
                            for c, v in zip(chunks, vectors, strict=True)
                        ],
                    )

    async def get_report(self, report_id: str) -> Report | None:
        async with self.pool.connection() as conn:
            row = await (
                await conn.execute("SELECT body FROM mars_reports WHERE id=%s", (report_id,))
            ).fetchone()
        return Report.model_validate(row[0]) if row else None

    async def list_reports(self, limit: int = 20, offset: int = 0) -> list[ReportSummary]:
        async with self.pool.connection() as conn:
            rows = await (
                await conn.execute(
                    """SELECT id, question, status, created_at,
                              jsonb_array_length(body->'sources'), jsonb_array_length(body->'warnings')
                       FROM mars_reports ORDER BY created_at DESC LIMIT %s OFFSET %s""",
                    (limit, offset),
                )
            ).fetchall()
        return [
            ReportSummary(id=r[0], question=r[1], status=r[2], created_at=r[3], sources=r[4], warnings=r[5])
            for r in rows
        ]

    async def delete_report(self, report_id: str) -> bool:
        async with self.pool.connection() as conn:
            cur = await conn.execute("DELETE FROM mars_reports WHERE id=%s", (report_id,))
            return cur.rowcount > 0

    async def search(self, query: str, k: int = 5, min_score: float = 0.0) -> list[ChunkHit]:
        q = np.asarray((await self.embedder.embed([query]))[0], np.float32)
        async with self.pool.connection() as conn:
            rows = await (
                await conn.execute(
                    """SELECT report_id, text, url, title, published, created_at,
                              1 - (embedding <=> %s) AS score
                       FROM mars_chunks ORDER BY embedding <=> %s LIMIT %s""",
                    (q, q, k),
                )
            ).fetchall()
        return [
            ChunkHit(
                report_id=r[0],
                text=r[1],
                url=r[2],
                title=r[3],
                published=r[4],
                indexed_at=r[5],
                score=float(r[6]),
            )
            for r in rows
            if r[6] >= min_score
        ]
