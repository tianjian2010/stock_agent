"""Application logging configuration."""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.config import (
    LOG_BACKUP_COUNT,
    LOG_FILE_ENABLED,
    LOG_FILE_PATH,
    LOG_LEVEL,
    LOG_MAX_BYTES,
)

LOG_FORMAT = "%(asctime)s %(levelname)-8s [%(name)s] %(message)s"
LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
CONSOLE_HANDLER_NAME = "stock_agent_console"
FILE_HANDLER_NAME = "stock_agent_file"
NOISY_LOGGERS = ("httpx", "chromadb", "openai")


def configure_logging() -> Path | None:
    """Configure root logging once for console and optional file output."""
    root_logger = logging.getLogger()
    level = getattr(logging, LOG_LEVEL, logging.INFO)
    formatter = logging.Formatter(LOG_FORMAT, datefmt=LOG_DATE_FORMAT)

    root_logger.setLevel(level)
    _ensure_console_handler(root_logger, level, formatter)

    log_file_path: Path | None = None
    if LOG_FILE_ENABLED:
        LOG_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
        _ensure_file_handler(root_logger, level, formatter, LOG_FILE_PATH)
        log_file_path = LOG_FILE_PATH

    for logger_name in NOISY_LOGGERS:
        logging.getLogger(logger_name).setLevel(logging.WARNING)

    return log_file_path


def _ensure_console_handler(
    root_logger: logging.Logger,
    level: int,
    formatter: logging.Formatter,
) -> None:
    console_handler = _find_handler(root_logger, CONSOLE_HANDLER_NAME)
    if console_handler is None:
        console_handler = logging.StreamHandler()
        console_handler.set_name(CONSOLE_HANDLER_NAME)
        root_logger.addHandler(console_handler)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)


def _ensure_file_handler(
    root_logger: logging.Logger,
    level: int,
    formatter: logging.Formatter,
    log_file_path: Path,
) -> None:
    expected_path = str(log_file_path.resolve())
    file_handler = _find_handler(root_logger, FILE_HANDLER_NAME)

    if file_handler is not None and getattr(file_handler, "baseFilename", "") != expected_path:
        root_logger.removeHandler(file_handler)
        file_handler.close()
        file_handler = None

    if file_handler is None:
        file_handler = RotatingFileHandler(
            log_file_path,
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.set_name(FILE_HANDLER_NAME)
        root_logger.addHandler(file_handler)

    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)


def _find_handler(root_logger: logging.Logger, handler_name: str) -> logging.Handler | None:
    for handler in root_logger.handlers:
        if handler.get_name() == handler_name:
            return handler
    return None
