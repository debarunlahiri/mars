"""Stored reports and semantic memory search."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from ..schemas import Report
from ..storage import ChunkHit, ReportSummary, Storage
from .models import ErrorResponse
from .security import authenticate

router = APIRouter(tags=["reports"])


def _storage(request: Request) -> Storage:
    app = request.app
    app.state.limiter.check(authenticate(request, app.state.settings))
    store = app.state.service.deps.storage
    if store is None:
        raise HTTPException(
            501, {"code": "storage_disabled", "detail": "Set MARS_DATABASE_URL or MARS_STORAGE_DB."}
        )
    return store


ERRORS: dict[int | str, dict] = {
    401: {"model": ErrorResponse, "description": "Missing or invalid API key"},
    429: {"model": ErrorResponse, "description": "Rate limit exceeded (see Retry-After)"},
    501: {"model": ErrorResponse, "description": "Storage is not configured"},
}
NOT_FOUND: dict[int | str, dict] = {404: {"model": ErrorResponse, "description": "Report not found"}}


@router.get(
    "/reports",
    response_model=list[ReportSummary],
    summary="List stored reports, newest first",
    responses=ERRORS,
)
async def list_reports(request: Request, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)):
    return await _storage(request).list_reports(limit, offset)


@router.get(
    "/reports/{report_id}",
    response_model=Report,
    summary="Get one stored report",
    responses={**ERRORS, **NOT_FOUND},
)
async def get_report(report_id: str, request: Request):
    """`report_id` is the `thread_id` returned when the research ran."""
    report = await _storage(request).get_report(report_id)
    if report is None:
        raise HTTPException(404, "Report not found")
    return report


@router.delete(
    "/reports/{report_id}",
    status_code=204,
    summary="Delete a report and its indexed quotes",
    responses={**ERRORS, **NOT_FOUND},
)
async def delete_report(report_id: str, request: Request):
    if not await _storage(request).delete_report(report_id):
        raise HTTPException(404, "Report not found")


@router.get(
    "/memory/search",
    response_model=list[ChunkHit],
    summary="Semantic search over stored, verified quotes",
    responses=ERRORS,
)
async def memory_search(
    request: Request,
    q: str = Query(min_length=3, max_length=500),
    k: int = Query(5, ge=1, le=20),
    min_score: float = Query(0.0, ge=-1.0, le=1.0),
):
    """Semantic search over verified quotes from every stored report."""
    return await _storage(request).search(q, k, min_score)
