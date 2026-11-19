"""Upload and manage internal documents (PDF, Word, PowerPoint, Excel, text, images)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request, UploadFile
from pydantic import BaseModel

from ..docs import SUPPORTED, DocHit, DocumentInfo, DocumentService
from .models import ErrorResponse
from .security import authenticate

router = APIRouter(tags=["documents"])


class UploadResult(BaseModel):
    name: str
    status: str  # indexed | duplicate | failed
    document: DocumentInfo | None = None
    error: str | None = None


def _docs(request: Request) -> DocumentService:
    app = request.app
    app.state.limiter.check(authenticate(request, app.state.settings))
    docs = app.state.service.deps.docs
    if docs is None:
        raise HTTPException(501, {"code": "documents_disabled", "detail": "Set MARS_DOCS_DB to enable documents."})
    return docs


ERRORS: dict[int | str, dict] = {
    401: {"model": ErrorResponse, "description": "Missing or invalid API key"},
    429: {"model": ErrorResponse, "description": "Rate limit exceeded (see Retry-After)"},
    501: {"model": ErrorResponse, "description": "Documents are not enabled (MARS_DOCS_DB)"},
}


@router.post(
    "/documents",
    response_model=list[UploadResult],
    summary="Upload and index documents",
    responses=ERRORS,
)
async def upload(files: list[UploadFile], request: Request):
    """Multipart upload (`files`, repeatable). Supported: PDF, .docx, .pptx, .xlsx, images, text/markdown/CSV/
    JSON/HTML. Each file is reported separately; one bad file does not fail the others."""
    docs = _docs(request)
    if len(files) > 20:
        raise HTTPException(413, {"code": "too_many_files", "detail": "At most 20 files per request"})
    limit = docs.settings.max_upload_mb * 1024 * 1024
    results = []
    for f in files:
        data = await f.read(limit + 1)  # never buffer more than the limit
        r = await docs.ingest(f.filename or "file", data)
        results.append(UploadResult(name=r.name, status=r.status, document=r.document, error=r.error))
    return results


@router.get("/documents/sync", summary="Folder auto-sync status and the last scan result", responses=ERRORS)
async def sync_status(request: Request):
    """`enabled=false` unless `MARS_DOCS_DIR` is set."""
    sync = _docs(request).sync
    return sync.status() if sync else {"enabled": False}


@router.post(
    "/documents/sync",
    summary="Scan the watched folder now",
    responses={**ERRORS, 409: {"model": ErrorResponse, "description": "No folder configured"}},
)
async def sync_now(request: Request):
    """Adds new files, re-indexes changed ones and removes deleted ones, then returns what changed."""
    sync = _docs(request).sync
    if sync is None:
        raise HTTPException(409, {"code": "sync_disabled", "detail": "Set MARS_DOCS_DIR to a folder to watch."})
    return await sync.sync_once()


@router.get("/documents", response_model=list[DocumentInfo], summary="List indexed documents", responses=ERRORS)
async def list_documents(request: Request):
    return await _docs(request).list()


@router.get("/documents/formats", summary="Supported file extensions and the compute device in use")
async def formats(request: Request):
    docs = _docs(request)
    return {"extensions": SUPPORTED, **docs.describe()}


@router.get(
    "/documents/search",
    response_model=list[DocHit],
    summary="Semantic search over the indexed documents",
    responses=ERRORS,
)
async def search_documents(
    request: Request,
    q: str = Query(min_length=2, max_length=500),
    k: int = Query(5, ge=1, le=20),
):
    return await _docs(request).search(q, k)


@router.delete(
    "/documents/{doc_id}",
    status_code=204,
    summary="Remove a document from the index",
    responses={**ERRORS, 404: {"model": ErrorResponse, "description": "Document not found"}},
)
async def delete_document(doc_id: str, request: Request):
    if not await _docs(request).delete(doc_id):
        raise HTTPException(404, "Document not found")
