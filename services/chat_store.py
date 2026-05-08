"""Chat storage abstractions for multiple database backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any


class BaseChatStore(ABC):
    """Abstract storage interface for chat history."""

    @abstractmethod
    def create_chat(self, thread_id: str, title: str | None = None) -> int:
        raise NotImplementedError

    @abstractmethod
    def get_chat(self, thread_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    @abstractmethod
    def update_chat_metadata(self, thread_id: str, metadata: dict[str, Any]) -> None:
        raise NotImplementedError

    @abstractmethod
    def update_chat_title(self, thread_id: str, title: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def add_message(
        self,
        thread_id: str,
        role: str,
        content: str,
        reasoning_content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> int:
        raise NotImplementedError

    @abstractmethod
    def get_messages(self, thread_id: str, limit: int = 50) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def get_all_chats(self, limit: int = 50) -> list[dict[str, Any]]:
        raise NotImplementedError

    @abstractmethod
    def delete_chat(self, thread_id: str) -> None:
        raise NotImplementedError

    @abstractmethod
    def close(self) -> None:
        raise NotImplementedError


def normalize_db_path(db_path: str | Path) -> Path:
    return db_path if isinstance(db_path, Path) else Path(db_path)
