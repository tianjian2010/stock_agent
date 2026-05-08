"""Admin API endpoints for managing the document index."""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import STOCK_DOCS_DIR
from services.doc_loader import DocumentLoader
from services.document_retriever import get_document_retriever

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


class ReindexResponse(BaseModel):
    status: str
    document_count: int
    chunk_count: int
    vector_ready: bool
    updated_files: int
    removed_files: int


class IndexStatsResponse(BaseModel):
    document_count: int
    chunk_count: int
    vector_ready: bool
    indexed: bool


class DocumentItem(BaseModel):
    filename: str
    topic: str
    published_at: str
    source: str
    size: int
    file_type: str


class UploadResultItem(BaseModel):
    filename: str
    status: str
    detail: str


class UploadDocumentsResponse(BaseModel):
    saved: list[UploadResultItem]
    skipped: list[UploadResultItem]
    index_result: ReindexResponse


def _normalize_reindex_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "status": result.get("status", "unknown"),
        "document_count": result.get("document_count", 0),
        "chunk_count": result.get("chunk_count", 0),
        "vector_ready": result.get("vector_ready", False),
        "updated_files": result.get("updated_files", 0),
        "removed_files": result.get("removed_files", 0),
    }


def _safe_upload_name(upload: UploadFile) -> str:
    filename = Path(upload.filename or "").name.strip()
    if not filename:
        raise HTTPException(status_code=400, detail="Uploaded file must have a filename.")
    return filename


def _save_upload(upload: UploadFile, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("wb") as output:
        shutil.copyfileobj(upload.file, output)


@router.get("/index", response_model=IndexStatsResponse)
def get_index_stats() -> dict[str, Any]:
    """Return current index statistics."""
    retriever = get_document_retriever()
    stats = retriever.get_stats()
    return {
        "document_count": stats.get("document_count", 0),
        "chunk_count": stats.get("chunk_count", 0),
        "vector_ready": stats.get("vector_ready", False),
        "indexed": retriever._indexed,
    }


@router.post("/reindex", response_model=ReindexResponse)
def trigger_reindex(background_tasks: BackgroundTasks) -> dict[str, Any]:
    """
    Trigger a full incremental reindex in the background and return immediately.
    Use /api/admin/index to poll for current stats.
    """

    def _run() -> None:
        try:
            retriever = get_document_retriever()
            retriever.index_documents_incremental()
        except Exception as exc:
            logger.error("Background reindex failed: %s", exc)

    background_tasks.add_task(_run)
    return {
        "status": "triggered",
        "document_count": 0,
        "chunk_count": 0,
        "vector_ready": False,
        "updated_files": 0,
        "removed_files": 0,
    }


@router.post("/reindex/sync", response_model=ReindexResponse)
def trigger_reindex_sync() -> dict[str, Any]:
    """Trigger a full incremental reindex synchronously (waits for completion)."""
    retriever = get_document_retriever()
    return _normalize_reindex_result(retriever.index_documents_incremental())


@router.get("/documents", response_model=list[DocumentItem])
def list_documents(keyword: str = "") -> list[dict[str, Any]]:
    """List indexed source documents for the management page."""
    retriever = get_document_retriever()
    return retriever.list_documents(keyword=keyword)


@router.post("/documents/upload", response_model=UploadDocumentsResponse)
def upload_documents(
    files: list[UploadFile] = File(...),
    overwrite: bool = Form(False),
) -> dict[str, Any]:
    """Upload files into stock_docs and incrementally index them."""
    loader = DocumentLoader()
    saved: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []

    for upload in files:
        filename = _safe_upload_name(upload)
        try:
            if not loader.is_supported_file(filename):
                skipped.append(
                    {
                        "filename": filename,
                        "status": "unsupported",
                        "detail": f"Unsupported file type: {Path(filename).suffix.lower()}",
                    }
                )
                continue

            destination = STOCK_DOCS_DIR / filename
            if destination.exists() and not overwrite:
                skipped.append(
                    {
                        "filename": filename,
                        "status": "exists",
                        "detail": "File already exists. Enable overwrite to replace it.",
                    }
                )
                continue

            _save_upload(upload, destination)
            saved.append(
                {
                    "filename": filename,
                    "status": "saved",
                    "detail": "Stored in stock_docs and ready for indexing.",
                }
            )
        finally:
            upload.file.close()

    index_result = {
        "status": "skipped",
        "document_count": 0,
        "chunk_count": 0,
        "vector_ready": False,
        "updated_files": 0,
        "removed_files": 0,
    }
    if saved:
        retriever = get_document_retriever()
        index_result = _normalize_reindex_result(retriever.index_documents_incremental())

    return {
        "saved": saved,
        "skipped": skipped,
        "index_result": index_result,
    }
