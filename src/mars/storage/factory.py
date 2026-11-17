from __future__ import annotations

from ..core.config import Settings
from ..core.logging import get_logger
from .base import Storage
from .embeddings import build_embedder

log = get_logger("storage")


async def open_storage(s: Settings) -> Storage | None:
    """Postgres+pgvector if MARS_DATABASE_URL is set, else SQLite if MARS_STORAGE_DB, else None."""
    if not (s.database_url or s.storage_db):
        return None
    embedder = build_embedder(s)
    store: Storage
    if s.database_url:
        from .postgres import PostgresStorage

        store = PostgresStorage(s.database_url, embedder)
    else:
        from .sqlite import SqliteStorage

        store = SqliteStorage(s.storage_db, embedder)
    await store.setup()
    log.info("storage ready: %s, embeddings=%s", "postgres" if s.database_url else "sqlite", embedder.name)
    return store
