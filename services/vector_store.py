"""Vector store service using ChromaDB."""

import logging
from pathlib import Path
from typing import Any

from app.config import ENABLE_VECTOR_SEARCH, VECTOR_STORE_PATH
from services.llm import create_embedding_model

logger = logging.getLogger(__name__)


class VectorStoreService:
    """ChromaDB-backed vector store."""

    def __init__(
        self,
        persist_directory: str | Path | None = None,
        collection_name: str = "stock_docs",
    ):
        self.persist_directory = Path(persist_directory or VECTOR_STORE_PATH)
        self.collection_name = collection_name
        self._client: Any = None
        self._collection: Any = None
        self._available: bool | None = None

    @property
    def enabled(self) -> bool:
        if not ENABLE_VECTOR_SEARCH:
            return False
        if not create_embedding_model().configured:
            return False
        if self._available is False:
            return False
        try:
            _ = self.client
        except Exception as exc:
            self._available = False
            logger.warning("Vector store unavailable, falling back to lexical retrieval: %s", exc)
            return False
        self._available = True
        return True

    @property
    def client(self) -> Any:
        if not ENABLE_VECTOR_SEARCH or not create_embedding_model().configured:
            raise RuntimeError("Vector search is disabled.")
        if self._client is None:
            import chromadb
            from chromadb.config import Settings

            self.persist_directory.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(
                path=str(self.persist_directory),
                settings=Settings(anonymized_telemetry=False, allow_reset=True),
            )
        return self._client

    @property
    def collection(self) -> Any:
        if self._collection is None:
            self._collection = self.client.get_or_create_collection(
                name=self.collection_name,
                metadata={"description": "Stock research document chunks"},
            )
        return self._collection

    def add_documents(
        self,
        documents: list[str],
        ids: list[str] | None = None,
        metadatas: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        if not self.enabled or not documents:
            return ids or []

        if ids is None:
            import uuid

            ids = [str(uuid.uuid4()) for _ in documents]

        embeddings = create_embedding_model().embed_documents(documents)
        self.collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )
        return ids

    def similarity_search(
        self,
        query: str,
        k: int = 5,
        filter_metadata: dict[str, Any] | None = None,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        if not self.enabled:
            return [], []

        query_embedding = create_embedding_model().embed_query(query)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
            where=filter_metadata,
        )
        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        return documents, metadatas

    def similarity_search_with_score(
        self,
        query: str,
        k: int = 5,
    ) -> list[tuple[str, float, dict[str, Any]]]:
        if not self.enabled:
            return []

        query_embedding = create_embedding_model().embed_query(query)
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=k,
        )
        documents = results.get("documents", [[]])[0]
        distances = results.get("distances", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        return [
            (doc, float(distance), metadata)
            for doc, distance, metadata in zip(documents, distances, metadatas)
        ]

    def delete(self, ids: list[str]) -> None:
        if self.enabled:
            self.collection.delete(ids=ids)

    def get_indexed_filenames(self) -> set[str]:
        """Return filenames currently present in the vector collection."""
        if not self.enabled:
            return set()

        results = self.collection.get(include=["metadatas"])
        metadatas = results.get("metadatas") or []
        return {
            str(metadata.get("filename"))
            for metadata in metadatas
            if metadata and metadata.get("filename")
        }

    def reset(self) -> None:
        if self.enabled:
            self.client.delete_collection(self.collection_name)
            self._collection = None


_vector_store: VectorStoreService | None = None


def get_vector_store() -> VectorStoreService:
    """Get the global vector store instance."""
    global _vector_store
    if _vector_store is None:
        _vector_store = VectorStoreService()
    return _vector_store
