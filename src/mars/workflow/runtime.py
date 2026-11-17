"""Opens the long-lived resources (storage, checkpointer) and builds the service around them."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

from ..core.config import Settings, get_settings
from ..core.logging import get_logger
from ..storage import open_storage
from .service import ResearchService
from .state import ALLOWED_TYPES

log = get_logger("runtime")


@dataclass
class Runtime:
    service: ResearchService
    _closers: list[Callable[[], Awaitable[None]]] = field(default_factory=list)

    async def aclose(self) -> None:
        await self.service.aclose()
        for close in reversed(self._closers):
            try:
                await close()
            except Exception:  # noqa: BLE001
                log.exception("error while closing a resource")


async def _open_checkpointer(s: Settings, closers: list):
    """Checkpoints hold in-flight/paused runs. Postgres > SQLite > memory."""
    serde = JsonPlusSerializer(allowed_msgpack_modules=ALLOWED_TYPES)
    if s.database_url:
        from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        from psycopg.rows import dict_row
        from psycopg_pool import AsyncConnectionPool

        pool = AsyncConnectionPool(
            s.database_url,
            max_size=5,
            open=False,
            kwargs={"autocommit": True, "prepare_threshold": 0, "row_factory": dict_row},
        )
        await pool.open(wait=True, timeout=15)
        closers.append(pool.close)
        saver = AsyncPostgresSaver(pool, serde=serde)
        await saver.setup()
        return saver
    if s.checkpoint_db:
        import aiosqlite
        from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

        conn = await aiosqlite.connect(s.checkpoint_db)
        closers.append(conn.close)
        saver = AsyncSqliteSaver(conn, serde=serde)
        await saver.setup()
        return saver
    return None  # build_graph falls back to the in-memory saver


async def open_runtime(settings: Settings | None = None) -> Runtime:
    s = settings or get_settings()
    closers: list[Callable[[], Awaitable[None]]] = []
    try:
        storage = await open_storage(s)
        if storage is not None:
            closers.append(storage.aclose)
        checkpointer = await _open_checkpointer(s, closers)
        service = ResearchService(s, checkpointer=checkpointer, storage=storage)
    except BaseException:
        for close in reversed(closers):
            await close()
        raise
    return Runtime(service, closers)
