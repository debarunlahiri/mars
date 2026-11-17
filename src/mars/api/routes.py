from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse

from ..schemas import Report
from ..workflow.service import ResearchService, run_to_completion
from .models import ApprovalRequest, ResearchRequest, ResearchResponse
from .security import authenticate

router = APIRouter()


def _admit(request: Request) -> ResearchService:
    """Authenticate, rate-limit and shed load before any expensive work starts."""
    app = request.app
    authenticate_identity = authenticate(request, app.state.settings)
    app.state.limiter.check(authenticate_identity)
    svc: ResearchService = app.state.service
    if svc.active >= app.state.settings.max_concurrent_runs:
        raise HTTPException(503, "Server is busy; retry shortly", headers={"Retry-After": "10"})
    return svc


def _sse(events: AsyncIterator[dict]) -> StreamingResponse:
    async def gen():
        async for ev in events:
            yield f"event: {ev['event']}\ndata: {json.dumps(ev, default=str)}\n\n"

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _response(last: dict) -> ResearchResponse:
    kind = last.get("event")
    thread_id = last.get("thread_id", "")
    if kind == "report":
        report = Report.model_validate(last["report"])
        return ResearchResponse(thread_id=thread_id, status=report.status, report=report)
    if kind == "awaiting_approval":
        return ResearchResponse(thread_id=thread_id, status="awaiting_approval", preview=last["preview"])
    raise HTTPException(
        last.get("status", 500),
        {"code": last.get("code", "internal_error"), "detail": last.get("detail", "")},
    )


async def _require_waiting(svc: ResearchService, thread_id: str) -> None:
    if not await svc.is_waiting(thread_id):
        raise HTTPException(404, "No research is awaiting approval for this thread_id")


@router.post("/research", response_model=ResearchResponse, tags=["research"])
async def research(req: ResearchRequest, request: Request):
    svc = _admit(request)
    return _response(await run_to_completion(svc.start(req.question, req.require_approval)))


@router.post("/research/stream", tags=["research"])
async def research_stream(req: ResearchRequest, request: Request):
    svc = _admit(request)
    return _sse(svc.start(req.question, req.require_approval))


@router.post("/research/{thread_id}/approve", response_model=ResearchResponse, tags=["research"])
async def approve(thread_id: str, req: ApprovalRequest, request: Request):
    svc = _admit(request)
    await _require_waiting(svc, thread_id)
    return _response(await run_to_completion(svc.resume(thread_id, req.approved, req.feedback)))


@router.post("/research/{thread_id}/approve/stream", tags=["research"])
async def approve_stream(thread_id: str, req: ApprovalRequest, request: Request):
    svc = _admit(request)
    await _require_waiting(svc, thread_id)
    return _sse(svc.resume(thread_id, req.approved, req.feedback))


@router.get("/health", tags=["ops"])
async def health(request: Request):
    s = request.app.state.settings
    return {
        "status": "ok",
        "provider": s.resolved_provider(),
        "search": s.resolved_search(),
        "active_runs": request.app.state.service.active,
        "storage": "postgres" if s.database_url else ("sqlite" if s.storage_db else "off"),
        "persistent": bool(s.database_url or s.checkpoint_db),
    }
