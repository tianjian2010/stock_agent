"""FastAPI server entry point."""

import logging
import os

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.chat import router as chat_router
from app.api.admin import router as admin_router
from app.config import LLM_STARTUP_HEALTHCHECK
from app.life import get_scheduler
from app.logging_setup import configure_logging
from services.document_retriever import get_document_retriever
from services.llm import diagnose_minimax_auth

LOG_FILE_PATH = configure_logging()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """FastAPI lifespan: fast startup + background indexing, then shutdown cleanup."""
    if LOG_FILE_PATH is not None:
        logging.info("File logging enabled: %s", LOG_FILE_PATH)
    if LLM_STARTUP_HEALTHCHECK:
        llm_diag = diagnose_minimax_auth()
        level = logging.INFO if llm_diag.get("ok") else logging.WARNING
        logging.log(
            level,
            "MiniMax startup health: ok=%s, category=%s, model=%s, base_url=%s, api_key=%s, source_base_url=%s, detail=%s",
            llm_diag.get("ok"),
            llm_diag.get("category"),
            llm_diag.get("model"),
            llm_diag.get("base_url"),
            llm_diag.get("api_key_preview"),
            llm_diag.get("base_url_source"),
            llm_diag.get("message"),
        )

    # Start background indexing without blocking API readiness.
    get_document_retriever()
    scheduler = get_scheduler()
    scheduler.start_periodic(get_document_retriever)
    logging.info("Startup indexing delegated to background scheduler.")
    logging.info("BACKEND READY: API can accept requests.")

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

    uvicorn.run(app, host="0.0.0.0", port=8000, log_config=None)
