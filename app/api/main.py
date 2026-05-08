"""FastAPI server entry point."""

import logging
import os

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.admin import router as admin_router
from app.life import get_scheduler
from services.document_retriever import get_document_retriever


# Configure logging so that all modules' logger.info/warning/error appear in console
_log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, _log_level, logging.INFO),
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
# Silence overly noisy libraries
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("chromadb").setLevel(logging.WARNING)
logging.getLogger("openai").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """FastAPI lifespan: startup indexing + periodic background refresh, shutdown cleanup."""
    # Startup: run initial incremental index
    retriever = get_document_retriever()
    result = retriever.index_documents_incremental()
    logging.info(
        "Startup indexing: status=%s, docs=%d, chunks=%d, vector_ready=%s, updated=%d",
        result.get("status"),
        result.get("document_count", 0),
        result.get("chunk_count", 0),
        result.get("vector_ready"),
        result.get("updated_files", 0),
    )

    # Start background periodic indexing
    scheduler = get_scheduler()
    scheduler.start_periodic(get_document_retriever)

    yield

    # Shutdown: stop the scheduler cleanly
    scheduler.stop()


app = FastAPI(title="Stock Agent API", version="1.0.0", lifespan=lifespan)

# Allow FRONTEND_ORIGINS env var, comma-separated, default to localhost dev ports
_frontend_origins = os.getenv(
    "FRONTEND_ORIGINS",
    "http://localhost:5173,http://localhost:3000,http://localhost:3001",
)
allow_origins = [origin.strip() for origin in _frontend_origins.split(",") if origin.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allow_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chat_router)
app.include_router(admin_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)