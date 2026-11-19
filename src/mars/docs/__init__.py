"""Internal documents: ingest PDF / Word / PowerPoint / Excel / text / images and search them."""

from .device import available_devices, resolve_device
from .extract import SUPPORTED, ExtractionError
from .service import DOC_SCHEME, DocumentService, IngestResult, is_doc_url, open_documents
from .store import DocHit, DocumentInfo, DocumentStore

__all__ = [
    "DOC_SCHEME",
    "SUPPORTED",
    "DocHit",
    "DocumentInfo",
    "DocumentService",
    "DocumentStore",
    "ExtractionError",
    "IngestResult",
    "available_devices",
    "is_doc_url",
    "open_documents",
    "resolve_device",
]
