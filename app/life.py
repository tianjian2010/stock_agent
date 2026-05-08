"""Background indexing tasks and FastAPI lifespan management."""

from __future__ import annotations

import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)

# Exposed so config can override
DEFAULT_INTERVAL = 300  # 5 minutes


def _interval() -> int:
    try:
        from app.config import INDEX_CHECK_INTERVAL_SECONDS
        return INDEX_CHECK_INTERVAL_SECONDS
    except Exception:
        return DEFAULT_INTERVAL


class IndexingScheduler:
    """Manages startup and periodic incremental index refreshes."""

    def __init__(self) -> None:
        self._stop_event: threading.Event | None = None
        self._thread: threading.Thread | None = None

    def start_periodic(
        self,
        retriever_getter: Any,
    ) -> None:
        """Start a background thread that re-runs incremental indexing every N seconds."""
        if self._thread is not None:
            logger.warning("IndexingScheduler already running – ignoring duplicate start")
            return

        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._periodic_loop,
            args=(retriever_getter,),
            daemon=True,
            name="IndexingScheduler",
        )
        self._thread.start()
        logger.info("IndexingScheduler started (interval=%ds)", _interval())

    def stop(self) -> None:
        """Signal the background thread to stop and wait for it to join."""
        if self._thread is None:
            return
        if self._stop_event is not None:
            self._stop_event.set()
        self._thread.join(timeout=10)
        self._thread = None
        self._stop_event = None
        logger.info("IndexingScheduler stopped")

    def _periodic_loop(self, retriever_getter: Any) -> None:
        """Run incremental indexing on a cadence, catching all exceptions silently."""
        stop_event = self._stop_event
        if stop_event is None:
            return

        # Perform an immediate first run before entering the wait loop
        self._run_once(retriever_getter)

        while True:
            stop_event.wait(timeout=_interval())
            if stop_event.is_set():
                break

            self._run_once(retriever_getter)

    def _run_once(self, retriever_getter: Any) -> None:
        """Execute a single incremental indexing pass with error logging."""
        try:
            retriever = retriever_getter()
            result = retriever.index_documents_incremental()
            logger.info(
                "Periodic index refresh: status=%s, docs=%d, chunks=%d, vector_ready=%s, updated=%d, removed=%d",
                result.get("status"),
                result.get("document_count", 0),
                result.get("chunk_count", 0),
                result.get("vector_ready"),
                result.get("updated_files", 0),
                result.get("removed_files", 0),
            )
        except Exception as exc:
            logger.error("Periodic indexing failed: %s", exc, exc_info=True)


# Global singleton with thread-safe initialization
_scheduler: IndexingScheduler | None = None
_scheduler_lock = threading.Lock()


def get_scheduler() -> IndexingScheduler:
    global _scheduler
    if _scheduler is None:
        with _scheduler_lock:
            # Double-check after acquiring lock
            if _scheduler is None:
                _scheduler = IndexingScheduler()
    return _scheduler
