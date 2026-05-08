"""Document indexing and retrieval services for stock research materials."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.config import (
    CHUNK_OVERLAP,
    CHUNK_SIZE,
    DOCUMENT_DEFAULT_YEAR,
    MAX_DOCUMENT_PREVIEW_CHARS,
    MAX_RETRIEVAL_RESULTS,
)
from services.doc_loader import DocumentLoader
from services.vector_store import get_vector_store

logger = logging.getLogger(__name__)

INDEX_STATE_FILE = "data/cache/.index_state.json"

DATE_PATTERN = re.compile(r"(?P<date>\d{4,8})")
KEYWORD_PATTERN = re.compile(r"[A-Za-z0-9]{2,}|[\u4e00-\u9fff]{2,}")
STOP_WORDS = {
    "关于",
    "哪些",
    "什么",
    "怎么",
    "如何",
    "请问",
    "告诉",
    "查询",
    "看看",
    "分析",
    "研究",
    "报告",
    "资料",
    "文档",
    "研报",
    "最新",
    "最近",
    "一个",
    "一下",
    "有没有",
    "帮我",
    "列出",
}


@dataclass(slots=True)
class RetrievalResult:
    content: str
    score: float
    metadata: dict[str, Any]


def parse_document_metadata(filename: str) -> dict[str, Any]:
    """Parse topic and date from a stock research document filename."""
    stem = Path(filename).stem
    topic = stem
    published_at = ""

    match = DATE_PATTERN.search(stem)
    if match:
        topic = stem[: match.start()].rstrip("-_ ")
        raw_date = match.group("date")
        year, month, day = _normalize_filename_date(raw_date)
        try:
            published_at = date(year, month, day).isoformat()
        except ValueError:
            published_at = ""

    return {
        "filename": filename,
        "topic": topic or stem,
        "published_at": published_at,
        "source_type": Path(filename).suffix.lower(),
    }


def _normalize_filename_date(raw_date: str) -> tuple[int, int, int]:
    if len(raw_date) == 8:
        return int(raw_date[:4]), int(raw_date[4:6]), int(raw_date[6:8])
    if len(raw_date) == 6:
        return 2000 + int(raw_date[:2]), int(raw_date[2:4]), int(raw_date[4:6])
    if len(raw_date) == 4:
        return DOCUMENT_DEFAULT_YEAR, int(raw_date[:2]), int(raw_date[2:4])
    raise ValueError(f"Unsupported date pattern: {raw_date}")


def extract_query_keywords(query: str, limit: int = 6) -> list[str]:
    keywords: list[str] = []
    normalized_query = query
    for stop_word in STOP_WORDS:
        normalized_query = normalized_query.replace(stop_word, " ")

    for token in KEYWORD_PATTERN.findall(normalized_query):
        token = token.strip()
        if len(token) < 2 or token in STOP_WORDS:
            continue
        if token not in keywords:
            keywords.append(token)
        if len(keywords) >= limit:
            break

    compact = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", query)
    if len(keywords) <= 1 and len(compact) >= 2:
        for size in (4, 3, 2):
            for index in range(0, max(0, len(compact) - size + 1)):
                candidate = compact[index : index + size]
                if candidate in STOP_WORDS or candidate in keywords:
                    continue
                keywords.append(candidate)
                if len(keywords) >= limit:
                    return keywords[:limit]

    if not keywords and query.strip():
        keywords.append(query.strip()[:8])
    return keywords


class DocumentRetriever:
    """Hybrid document retriever with vector and lexical fallback."""

    def __init__(
        self,
        loader: DocumentLoader | None = None,
        chunk_size: int = CHUNK_SIZE,
        chunk_overlap: int = CHUNK_OVERLAP,
    ):
        self.loader = loader or DocumentLoader(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        self.vector_store = get_vector_store()
        self._indexed = False
        self._vector_ready = False
        self._documents: list[dict[str, Any]] = []
        self._chunks: list[dict[str, Any]] = []
        self._chunk_lookup: dict[str, dict[str, Any]] = {}

    def index_documents(self, force: bool = False) -> dict[str, Any]:
        """Load, chunk, and optionally vector-index the local document corpus."""
        if self._indexed and not force:
            return {
                "status": "ready",
                "document_count": len(self._documents),
                "chunk_count": len(self._chunks),
                "vector_ready": self._vector_ready,
            }

        self._documents = self.loader.scan_directories()
        self._chunks = []
        self._chunk_lookup = {}
        self._vector_ready = False

        for document in self._documents:
            self._append_document_chunks(document)

        if self._chunks and self.vector_store.enabled:
            try:
                self.vector_store.reset()
                self.vector_store.add_documents(
                    [chunk["content"] for chunk in self._chunks],
                    ids=[chunk["metadata"]["chunk_uid"] for chunk in self._chunks],
                    metadatas=[chunk["metadata"] for chunk in self._chunks],
                )
                self._vector_ready = True
            except Exception as exc:
                logger.warning("Vector indexing unavailable, fallback to lexical retrieval: %s", exc)

        self._indexed = True
        return {
            "status": "indexed",
            "document_count": len(self._documents),
            "chunk_count": len(self._chunks),
            "vector_ready": self._vector_ready,
        }

    def _append_document_chunks(self, document: dict[str, Any]) -> list[dict[str, Any]]:
        path = Path(document["metadata"]["source"])
        metadata = parse_document_metadata(document["metadata"]["filename"])
        file_chunks = self.loader.load_and_chunk(path)
        items: list[dict[str, Any]] = []
        for chunk in file_chunks:
            chunk_metadata = {
                **chunk["metadata"],
                **metadata,
                "chunk_uid": f"{metadata['filename']}::{chunk['metadata']['chunk_id']}",
            }
            item = {"content": chunk["content"], "metadata": chunk_metadata}
            items.append(item)
            self._chunk_lookup[chunk_metadata["chunk_uid"]] = item

        self._chunks.extend(items)
        return items

    # -------------------------------------------------------------------------
    # Incremental indexing
    # -------------------------------------------------------------------------

    def _index_state_path(self) -> Path:
        from app.config import PROJECT_ROOT

        return PROJECT_ROOT / INDEX_STATE_FILE

    def _load_index_state(self) -> dict[str, dict[str, Any]]:
        path = self._index_state_path()
        if not path.exists():
            return {}
        try:
            with open(path, "r", encoding="utf-8") as handle:
                return json.load(handle)
        except Exception as exc:
            logger.warning("Failed to load index state: %s", exc)
            return {}

    def _save_index_state(self, state: dict[str, dict[str, Any]]) -> None:
        path = self._index_state_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(path, "w", encoding="utf-8") as handle:
                json.dump(state, handle, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("Failed to save index state: %s", exc)

    def _build_index_state(self) -> dict[str, dict[str, Any]]:
        """Build a map of filename -> index entry for all currently loaded documents."""
        state: dict[str, dict[str, Any]] = {}
        for doc in self._documents:
            source = doc["metadata"]["source"]
            path = Path(source)
            state[path.name] = {
                "source": source,
                "size": doc["metadata"].get("size", 0),
                "mtime": path.stat().st_mtime if path.exists() else 0,
            }
        return state

    def index_documents_incremental(self) -> dict[str, Any]:
        """
        Load all documents, then upsert only those that are new, changed,
        or missing from the vector store.
        """
        all_documents = self.loader.scan_directories()
        prior_state = self._load_index_state()
        indexed_filenames = (
            self.vector_store.get_indexed_filenames() if self.vector_store.enabled else set()
        )

        self._documents = all_documents
        self._chunks = []
        self._chunk_lookup = {}
        self._vector_ready = False

        new_or_modified: list[dict[str, Any]] = []
        current_names: set[str] = set()

        for doc in all_documents:
            source = doc["metadata"]["source"]
            path = Path(source)
            name = path.name
            current_names.add(name)

            entry = prior_state.get(name)
            if entry is None:
                new_or_modified.append(doc)
                continue

            try:
                current_mtime = path.stat().st_mtime
                current_size = doc["metadata"].get("size", 0)
                needs_reindex = (
                    current_mtime != entry.get("mtime")
                    or current_size != entry.get("size")
                    or (self.vector_store.enabled and name not in indexed_filenames)
                )
                if needs_reindex:
                    new_or_modified.append(doc)
                else:
                    self._restore_chunks_from_state(doc, name)
            except OSError:
                new_or_modified.append(doc)

        stale_names = set(prior_state.keys()) - current_names

        rebuilt_for_stale = False
        if stale_names and self.vector_store.enabled:
            self._remove_stale_chunks(stale_names)
            rebuilt_for_stale = True

        if rebuilt_for_stale:
            pass
        elif new_or_modified:
            self._reindex_new_or_modified(new_or_modified)
        elif not stale_names and prior_state:
            self._vector_ready = self.vector_store.enabled and bool(indexed_filenames)
            if self.vector_store.enabled and not self._vector_ready:
                self._reindex_new_or_modified(all_documents)
        elif not prior_state:
            self._vector_ready = self.vector_store.enabled and bool(indexed_filenames)

        self._save_index_state(self._build_index_state())
        self._indexed = True

        return {
            "status": "incremental",
            "document_count": len(self._documents),
            "chunk_count": len(self._chunks),
            "vector_ready": self._vector_ready,
            "updated_files": len(new_or_modified),
            "removed_files": len(stale_names),
        }

    def _restore_chunks_from_state(self, doc: dict[str, Any], filename: str) -> None:
        """Re-populate in-memory chunks for an unchanged file."""
        path = Path(doc["metadata"]["source"])
        metadata = parse_document_metadata(filename)
        file_chunks = self.loader.load_and_chunk(path)
        for chunk in file_chunks:
            chunk_metadata = {
                **chunk["metadata"],
                **metadata,
                "chunk_uid": f"{metadata['filename']}::{chunk['metadata']['chunk_id']}",
            }
            item = {"content": chunk["content"], "metadata": chunk_metadata}
            self._chunks.append(item)
            self._chunk_lookup[chunk_metadata["chunk_uid"]] = item

    def _reindex_new_or_modified(self, docs: list[dict[str, Any]]) -> None:
        """Re-chunk and upsert the given documents into the vector store."""
        new_chunks: list[dict[str, Any]] = []
        for doc in docs:
            path = Path(doc["metadata"]["source"])
            metadata = parse_document_metadata(doc["metadata"]["filename"])
            file_chunks = self.loader.load_and_chunk(path)
            for chunk in file_chunks:
                chunk_metadata = {
                    **chunk["metadata"],
                    **metadata,
                    "chunk_uid": f"{metadata['filename']}::{chunk['metadata']['chunk_id']}",
                }
                item = {"content": chunk["content"], "metadata": chunk_metadata}
                new_chunks.append(item)
                self._chunk_lookup[chunk_metadata["chunk_uid"]] = item

        if not new_chunks:
            return

        self._chunks.extend(new_chunks)

        if not self.vector_store.enabled:
            return

        try:
            self.vector_store.add_documents(
                [chunk["content"] for chunk in new_chunks],
                ids=[chunk["metadata"]["chunk_uid"] for chunk in new_chunks],
                metadatas=[chunk["metadata"] for chunk in new_chunks],
            )
            self._vector_ready = True
        except Exception as exc:
            logger.warning("Incremental vector upsert failed, keeping lexical-only: %s", exc)

    def _remove_stale_chunks(self, stale_names: set[str]) -> None:
        """Delete chunk entries for removed files by rebuilding the index."""
        logger.info("Removing %d stale file(s) from index; triggering full rebuild", len(stale_names))
        self.vector_store.reset()
        self._chunks = []
        self._chunk_lookup = {}
        self._vector_ready = False

        for doc in self._documents:
            self._append_document_chunks(doc)

        if self._chunks:
            try:
                self.vector_store.add_documents(
                    [chunk["content"] for chunk in self._chunks],
                    ids=[chunk["metadata"]["chunk_uid"] for chunk in self._chunks],
                    metadatas=[chunk["metadata"] for chunk in self._chunks],
                )
                self._vector_ready = True
            except Exception as exc:
                logger.warning("Full rebuild vector index failed: %s", exc)

    def get_stats(self) -> dict[str, Any]:
        if not self._indexed:
            return self.index_documents_incremental()
        return {
            "document_count": len(self._documents),
            "chunk_count": len(self._chunks),
            "vector_ready": self._vector_ready,
        }

    def list_documents(self, keyword: str = "") -> list[dict[str, Any]]:
        if not self._indexed:
            self.index_documents_incremental()

        docs = []
        keyword_lower = keyword.lower()
        for document in self._documents:
            metadata = {
                **document["metadata"],
                **parse_document_metadata(document["metadata"]["filename"]),
            }
            if keyword_lower:
                in_filename = keyword_lower in metadata["filename"].lower()
                in_topic = keyword_lower in metadata["topic"].lower()
                if not in_filename and not in_topic:
                    continue
            docs.append(metadata)

        docs.sort(key=lambda item: (item.get("published_at") or "", item["filename"]), reverse=True)
        return docs

    def find_latest_documents(self) -> list[dict[str, Any]]:
        docs = self.list_documents()
        latest_date = next((item["published_at"] for item in docs if item.get("published_at")), "")
        if not latest_date:
            return []
        return [item for item in docs if item.get("published_at") == latest_date]

    def get_document(self, filename: str) -> dict[str, Any] | None:
        if not self._indexed:
            self.index_documents_incremental()

        for document in self._documents:
            if document["metadata"]["filename"] == filename:
                return {
                    "content": document["content"],
                    "metadata": {
                        **document["metadata"],
                        **parse_document_metadata(filename),
                    },
                }
        return None

    def search(self, query: str, k: int = MAX_RETRIEVAL_RESULTS) -> list[RetrievalResult]:
        if not self._indexed:
            self.index_documents_incremental()
        if not query.strip():
            return []

        results = self._vector_search(query, k)
        if results:
            return results
        return self._lexical_search(query, k)

    def build_context(
        self,
        results: list[RetrievalResult],
        max_chars: int = MAX_DOCUMENT_PREVIEW_CHARS,
    ) -> str:
        if not results:
            return ""

        lines = ["本地投研资料摘录："]
        for index, item in enumerate(results, start=1):
            metadata = item.metadata
            published_at = metadata.get("published_at") or "未知日期"
            chunk_label = f"{metadata.get('chunk_id', 0) + 1}/{metadata.get('total_chunks', 1)}"
            preview = item.content.strip().replace("\n", " ")
            if len(preview) > max_chars:
                preview = preview[:max_chars].rstrip() + "..."
            lines.append(
                f"[资料{index}] {metadata.get('filename', '')} | {published_at} | 分片 {chunk_label}"
            )
            lines.append(preview)
        return "\n".join(lines)

    def _vector_search(self, query: str, k: int) -> list[RetrievalResult]:
        if not self._vector_ready:
            return []

        try:
            vector_hits = self.vector_store.similarity_search_with_score(query, k=k)
        except Exception as exc:
            logger.warning("Vector search failed, fallback to lexical retrieval: %s", exc)
            return []

        results: list[RetrievalResult] = []
        for content, distance, metadata in vector_hits:
            score = max(0.0, 1.0 - float(distance))
            results.append(RetrievalResult(content=content, score=score, metadata=metadata))
        return results

    def _lexical_search(self, query: str, k: int) -> list[RetrievalResult]:
        keywords = extract_query_keywords(query)
        query_lower = query.lower()
        ranked: list[RetrievalResult] = []

        for chunk in self._chunks:
            metadata = chunk["metadata"]
            filename_lower = metadata.get("filename", "").lower()
            topic_lower = metadata.get("topic", "").lower()
            content_lower = chunk["content"].lower()

            score = 0.0
            if query_lower in filename_lower or query_lower in topic_lower:
                score += 25
            for keyword in keywords:
                keyword_lower = keyword.lower()
                if keyword_lower in filename_lower:
                    score += 15
                if keyword_lower in topic_lower:
                    score += 10
                count = content_lower.count(keyword_lower)
                if count:
                    score += min(count, 8) * 2
                    if keyword_lower in content_lower[:200]:
                        score += 3

            if score > 0:
                ranked.append(
                    RetrievalResult(
                        content=chunk["content"],
                        score=score,
                        metadata=metadata,
                    )
                )

        ranked.sort(
            key=lambda item: (
                item.score,
                item.metadata.get("published_at") or "",
                item.metadata.get("filename") or "",
            ),
            reverse=True,
        )
        return ranked[:k]


_document_retriever: DocumentRetriever | None = None


def get_document_retriever() -> DocumentRetriever:
    global _document_retriever
    if _document_retriever is None:
        _document_retriever = DocumentRetriever()
    return _document_retriever
