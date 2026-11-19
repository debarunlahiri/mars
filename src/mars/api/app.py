"""FastAPI application factory."""

from __future__ import annotations

import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

from .. import __version__
from ..core.config import Settings, get_settings
from ..core.logging import get_logger, setup_logging
from ..workflow.runtime import open_runtime
from ..workflow.service import ResearchService
from .documents import router as documents_router
from .reports import router as reports_router
from .routes import router
from .security import RateLimiter
from .ui import INDEX_HTML

log = get_logger("api")


def create_app(settings: Settings | None = None, service: ResearchService | None = None) -> FastAPI:
    s = settings or get_settings()
    setup_logging(s.log_level, s.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        runtime = None
        if service is not None:
            app.state.service = service
        else:
            runtime = await open_runtime(s)
            app.state.service = runtime.service
        log.info(
            "started provider=%s search=%s storage=%s checkpoints=%s memory=%s auth=%s",
            s.resolved_provider(),
            s.resolved_search(),
            "postgres" if s.database_url else ("sqlite" if s.storage_db else "off"),
            "postgres" if s.database_url else ("sqlite" if s.checkpoint_db else "memory"),
            s.use_memory,
            bool(s.api_key_list),
        )
        if not s.api_key_list:
            log.warning("MARS_API_KEYS is empty: the API is unauthenticated (fine for local dev only)")
        try:
            yield
        finally:
            if runtime is not None:
                await runtime.aclose()
            else:
                await app.state.service.aclose()

    app = FastAPI(
        title="MARS - Multi-Agent Research System",
        version=__version__,
        description=(
            "Plans, researches the web, verifies claims against source text and writes cited reports.\n\n"
            "Authenticate with `X-API-Key: <key>` or `Authorization: Bearer <key>` when "
            "`MARS_API_KEYS` is set. Full reference: docs/api.md."
        ),
        openapi_tags=[
            {"name": "research", "description": "Run research jobs (blocking or streaming) and approve paused runs."},
            {"name": "reports", "description": "Stored reports and semantic search (needs storage configured)."},
            {"name": "documents", "description": "Upload PDF/Word/PowerPoint/Excel/image/text files; research cites them."},
            {"name": "ops", "description": "Health."},
        ],
        lifespan=lifespan,
    )
    app.state.settings = s
    app.state.limiter = RateLimiter(s.rate_limit_per_min)

    if s.cors_origin_list:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=s.cors_origin_list,
            allow_methods=["GET", "POST", "DELETE"],
            allow_headers=["*"],
        )

    @app.middleware("http")
    async def access_log(request: Request, call_next):
        rid = request.headers.get("x-request-id") or uuid.uuid4().hex[:12]
        start = time.monotonic()
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        log.info(
            "%s %s -> %s (%.0fms) rid=%s",
            request.method,
            request.url.path,
            response.status_code,
            (time.monotonic() - start) * 1000,
            rid,
        )
        return response

    @app.exception_handler(HTTPException)
    async def http_error(_: Request, exc: HTTPException):
        detail = exc.detail if isinstance(exc.detail, dict) else {"code": "error", "detail": exc.detail}
        return JSONResponse(detail, status_code=exc.status_code, headers=exc.headers)

    @app.get("/", include_in_schema=False)
    async def index():
        return HTMLResponse(INDEX_HTML)

    app.include_router(router)
    app.include_router(reports_router)
    app.include_router(documents_router)
    return app


def get_app() -> FastAPI:
    """ASGI entrypoint used by uvicorn: ``uvicorn mars.api.app:get_app --factory``."""
    return create_app()
