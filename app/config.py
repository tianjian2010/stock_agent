"""Application configuration."""

import os
from datetime import date
from pathlib import Path


def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _get_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


PROJECT_ROOT = Path(__file__).resolve().parent.parent
_load_dotenv(PROJECT_ROOT / ".env")
DATA_DIR = PROJECT_ROOT / "data"
DOCS_DIR = DATA_DIR / "docs"
CACHE_DIR = DATA_DIR / "cache"
VECTOR_STORE_PATH = CACHE_DIR / "vectorstore"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

STOCK_DOCS_DIR = PROJECT_ROOT / "stock_docs"
STOCK_DOCS_PATHS = [STOCK_DOCS_DIR]
TRANSCRIPTS_DIR = DATA_DIR / "transcripts"

MINIMAX_API_KEY = os.getenv("MINIMAX_API_KEY", "").strip()
MINIMAX_GROUP_ID = os.getenv("MINIMAX_GROUP_ID", "").strip()
MINIMAX_MODEL = os.getenv("MINIMAX_MODEL", "MiniMax-M2.7").strip()
MINIMAX_BASE_URL = os.getenv("MINIMAX_BASE_URL", "https://api.minimaxi.com/v1").strip()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o").strip()
DEFAULT_LLM_PROVIDER = os.getenv("DEFAULT_LLM_PROVIDER", "minimax").strip()

MX_API_KEY = os.getenv("MX_API_KEY", os.getenv("MX_APIKEY", "")).strip()
MX_DATA_URL = os.getenv(
    "MX_DATA_URL",
    "https://mkapi2.dfcfs.com/finskillshub/api/claw/query",
).strip()
MX_SEARCH_URL = os.getenv(
    "MX_SEARCH_URL",
    "https://mkapi2.dfcfs.com/finskillshub/api/claw/news-search",
).strip()
MX_SELECT_URL = os.getenv(
    "MX_SELECT_URL",
    "https://mkapi2.dfcfs.com/finskillshub/api/claw/stock-screen",
).strip()

EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "minimax").strip().lower()
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "MiniMax-embedding-01").strip()
_embedding_dimension_raw = os.getenv("EMBEDDING_DIMENSION", "").strip()
EMBEDDING_DIMENSION = int(_embedding_dimension_raw) if _embedding_dimension_raw else None
EMBEDDING_BASE_URL = os.getenv("EMBEDDING_BASE_URL", "").strip()
EMBEDDING_API_KEY = os.getenv("EMBEDDING_API_KEY", "").strip()
ENABLE_VECTOR_SEARCH = _get_bool("ENABLE_VECTOR_SEARCH", True)

CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "1000"))
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "200"))
MAX_RETRIEVAL_RESULTS = int(os.getenv("MAX_RETRIEVAL_RESULTS", "5"))
MAX_DOCUMENT_PREVIEW_CHARS = int(os.getenv("MAX_DOCUMENT_PREVIEW_CHARS", "700"))
DOCUMENT_DEFAULT_YEAR = int(os.getenv("DOCUMENT_DEFAULT_YEAR", str(date.today().year)))
MAX_SPREADSHEET_ROWS = int(os.getenv("MAX_SPREADSHEET_ROWS", "100"))
MAX_SPREADSHEET_COLS = int(os.getenv("MAX_SPREADSHEET_COLS", "30"))

if not DATABASE_URL:
    raise ValueError("DATABASE_URL is required for the PostgreSQL-backed application.")

STOCK_SKILLS_DIR = PROJECT_ROOT / "skills"

STREAMLIT_PORT = int(os.getenv("STREAMLIT_PORT", "8501"))
DEBUG_MODE = _get_bool("DEBUG", False)

MAX_CONVERSATION_HISTORY = int(os.getenv("MAX_CONVERSATION_HISTORY", "20"))
MAX_CONTEXT_TOKENS = int(os.getenv("MAX_CONTEXT_TOKENS", "4000"))
MEMORY_SUMMARY_TRIGGER_MESSAGES = int(os.getenv("MEMORY_SUMMARY_TRIGGER_MESSAGES", "6"))
MEMORY_SUMMARY_MAX_AGE_HOURS = int(os.getenv("MEMORY_SUMMARY_MAX_AGE_HOURS", "24"))
MEMORY_SUMMARY_MAX_CHARS = int(os.getenv("MEMORY_SUMMARY_MAX_CHARS", "800"))
MEMORY_SUMMARY_BATCH_SIZE = int(os.getenv("MEMORY_SUMMARY_BATCH_SIZE", "12"))
ENABLE_LLM_PLANNER = _get_bool("ENABLE_LLM_PLANNER", True)
LLM_PLANNER_MAX_STAGES = int(os.getenv("LLM_PLANNER_MAX_STAGES", "6"))
PLAN_REUSE_MAX_AGE_HOURS = int(os.getenv("PLAN_REUSE_MAX_AGE_HOURS", "6"))
PLAN_REUSE_MIN_SCORE = float(os.getenv("PLAN_REUSE_MIN_SCORE", "0.55"))

# MiniMax M2.7 does NOT support the "thinking" (reasoning) parameter.
# Set to true only if using a model that supports it (e.g. MiniMax-Text-01).
THINKING_ENABLED = _get_bool("THINKING_ENABLED", False)

INDEX_CHECK_INTERVAL_SECONDS = int(os.getenv("INDEX_CHECK_INTERVAL_SECONDS", "300"))
