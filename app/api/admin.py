"""Admin API endpoints for managing the document index."""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.config import DOCUMENT_DEFAULT_YEAR, STOCK_DOCS_DIR
from scripts.preprocess_docs import (
    CANONICAL_PATTERN,
    _extract_version,
    _parse_topic_and_date,
    _sanitize_topic,
    canonical_name,
    hash_file,
)
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


def _collect_existing_upload_state() -> tuple[dict[tuple[str, str], int], dict[tuple[str, str], set[str]]]:
    """Collect per-topic-date max version and content hashes from existing files."""
    max_versions: dict[tuple[str, str], int] = {}
    hash_index: dict[tuple[str, str], set[str]] = {}

    for path in STOCK_DOCS_DIR.iterdir():
        if not path.is_file():
            continue
        stem = path.stem

        canonical_match = CANONICAL_PATTERN.fullmatch(stem)
        if canonical_match:
            topic = _sanitize_topic(canonical_match.group("topic"))
            published_at = canonical_match.group("date")
            version = int(canonical_match.group("version"))
        else:
            stem_no_version, version_hint = _extract_version(stem)
            topic_raw, published_at, _, _, _ = _parse_topic_and_date(
                stem_no_version, DOCUMENT_DEFAULT_YEAR
            )
            if not published_at:
                continue
            topic = _sanitize_topic(topic_raw)
            version = max(1, version_hint)

        key = (topic, published_at)
        max_versions[key] = max(max_versions.get(key, 0), version)
        try:
            file_hash = hash_file(path)
        except Exception:
            continue
        hash_index.setdefault(key, set()).add(file_hash)

    return max_versions, hash_index


def _resolve_preprocessed_destination(
    original_name: str,
    *,
    overwrite: bool,
    max_versions: dict[tuple[str, str], int],
) -> tuple[Path | None, dict[str, str] | None]:
    """Return canonical destination path or a structured skip reason."""
    source_path = Path(original_name)
    stem = source_path.stem
    suffix = source_path.suffix.lower()

    canonical_match = CANONICAL_PATTERN.fullmatch(stem)
    if canonical_match:
        topic = _sanitize_topic(canonical_match.group("topic"))
        published_at = canonical_match.group("date")
        requested_version = int(canonical_match.group("version"))
        target_name = canonical_name(topic, published_at, requested_version, suffix)
        target_path = STOCK_DOCS_DIR / target_name
        if target_path.exists() and not overwrite:
            return None, {
                "status": "exists",
                "detail": "Canonical target already exists. Enable overwrite or use a new version.",
            }
        max_versions[(topic, published_at)] = max(
            max_versions.get((topic, published_at), 0),
            requested_version,
        )
        return target_path, None

    stem_no_version, _ = _extract_version(stem)
    topic_raw, published_at, _, _, parse_reason = _parse_topic_and_date(
        stem_no_version,
        DOCUMENT_DEFAULT_YEAR,
    )
    if not published_at:
        reason = parse_reason or "no_date_pattern"
        return None, {
            "status": "invalid_name",
            "detail": (
                f"Filename preprocessing failed ({reason}). "
                "Please include a date like 0508 or 2026-05-08."
            ),
        }

    topic = _sanitize_topic(topic_raw)
    key = (topic, published_at)
    next_version = max_versions.get(key, 0) + 1
    max_versions[key] = next_version
    target_name = canonical_name(topic, published_at, next_version, suffix)
    return STOCK_DOCS_DIR / target_name, None


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
    """Upload files with preprocessing, then run incremental indexing."""
    loader = DocumentLoader()
    saved: list[dict[str, str]] = []
    skipped: list[dict[str, str]] = []
    max_versions, hash_index = _collect_existing_upload_state()

    for upload in files:
        filename = _safe_upload_name(upload)
        staging_file: Path | None = None
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

            with tempfile.NamedTemporaryFile(
                dir=STOCK_DOCS_DIR,
                prefix=f".upload_staging_{uuid4().hex}_",
                suffix=Path(filename).suffix,
                delete=False,
            ) as tmp:
                staging_file = Path(tmp.name)
                shutil.copyfileobj(upload.file, tmp)

            try:
                content_hash = hash_file(staging_file)
            except Exception as exc:
                skipped.append(
                    {
                        "filename": filename,
                        "status": "error",
                        "detail": f"Failed to hash uploaded file: {exc}",
                    }
                )
                continue

            destination, preprocess_error = _resolve_preprocessed_destination(
                filename,
                overwrite=overwrite,
                max_versions=max_versions,
            )
            if preprocess_error is not None or destination is None:
                skipped.append(
                    {
                        "filename": filename,
                        "status": preprocess_error["status"] if preprocess_error else "invalid_name",
                        "detail": preprocess_error["detail"] if preprocess_error else "Filename preprocessing failed.",
                    }
                )
                continue

            canonical_match = CANONICAL_PATTERN.fullmatch(destination.stem)
            if canonical_match is None:
                skipped.append(
                    {
                        "filename": filename,
                        "status": "invalid_name",
                        "detail": "Failed to build canonical filename for uploaded file.",
                    }
                )
                continue
            dedup_key = (
                _sanitize_topic(canonical_match.group("topic")),
                canonical_match.group("date"),
            )
            known_hashes = hash_index.get(dedup_key, set())
            if content_hash in known_hashes:
                skipped.append(
                    {
                        "filename": filename,
                        "status": "duplicate",
                        "detail": "Exact duplicate content already exists for the same topic/date.",
                    }
                )
                continue

            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(staging_file), str(destination))
            staging_file = None
            hash_index.setdefault(dedup_key, set()).add(content_hash)
            saved.append(
                {
                    "filename": destination.name,
                    "status": "saved",
                    "detail": f"Preprocessed from {filename} and stored for indexing.",
                }
            )
        finally:
            if staging_file is not None and staging_file.exists():
                try:
                    staging_file.unlink()
                except OSError:
                    logger.warning("Failed to clean upload staging file: %s", staging_file)
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
