"""PostgreSQL-backed chat storage."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from app.config import DATABASE_URL
from services.chat_store import BaseChatStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DatabaseSettings:
    """Resolved runtime database settings."""

    database_url: str

    @property
    def display_name(self) -> str:
        return "PostgreSQL"

    @property
    def target(self) -> str:
        return self.database_url


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def resolve_database_settings(database_url: str | None = None) -> DatabaseSettings:
    """Resolve and validate PostgreSQL configuration."""
    url_value = (database_url if database_url is not None else DATABASE_URL).strip()
    if not url_value:
        raise ValueError("DATABASE_URL is required.")
    return DatabaseSettings(database_url=url_value)


def describe_database_settings(settings: DatabaseSettings | None = None) -> str:
    """Build a compact human-readable runtime database description."""
    resolved = settings or resolve_database_settings()
    return f"{resolved.display_name}: {resolved.target}"


def _build_postgres_store(database_url: str) -> BaseChatStore:
    from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, create_engine, delete, desc, select, update
    from sqlalchemy.engine import Engine
    from sqlalchemy.exc import SQLAlchemyError
    from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker

    globals()["Mapped"] = Mapped

    class Base(DeclarativeBase):
        pass

    class ChatRecord(Base):
        __tablename__ = "chats"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        thread_id: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
        title: Mapped[str | None] = mapped_column(String(255), nullable=True)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
        updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
        metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)
        messages: Mapped[list["MessageRecord"]] = relationship(
            back_populates="chat",
            cascade="all, delete-orphan",
        )

    class MessageRecord(Base):
        __tablename__ = "messages"

        id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
        chat_id: Mapped[int] = mapped_column(
            Integer,
            ForeignKey("chats.id", ondelete="CASCADE"),
            index=True,
            nullable=False,
        )
        role: Mapped[str] = mapped_column(String(50), nullable=False)
        content: Mapped[str] = mapped_column(Text, nullable=False)
        reasoning_content: Mapped[str | None] = mapped_column(Text, nullable=True)
        created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
        metadata_json: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, nullable=False, default=dict)
        chat: Mapped[ChatRecord] = relationship(back_populates="messages")

    class PostgresChatStore(BaseChatStore):
        def __init__(self, url: str):
            self.database_url = url
            self._engine: Engine = create_engine(
                url,
                future=True,
                pool_pre_ping=True,
            )
            self._session_factory = sessionmaker(
                bind=self._engine, future=True, expire_on_commit=False
            )
            self._init_db()

        def _init_db(self) -> None:
            try:
                Base.metadata.create_all(self._engine)
            except SQLAlchemyError:
                logger.exception("Failed to initialize PostgreSQL schema")
                raise

        def create_chat(self, thread_id: str, title: str | None = None) -> int:
            with self._session_factory() as session:
                existing = self._get_chat_record(session, thread_id)
                if existing is not None:
                    return int(existing.id)

                now = _utc_now()
                chat = ChatRecord(
                    thread_id=thread_id,
                    title=title or "新对话",
                    created_at=now,
                    updated_at=now,
                    metadata_json={},
                )
                session.add(chat)
                session.commit()
                session.refresh(chat)
                return int(chat.id)

        def get_chat(self, thread_id: str) -> dict[str, Any] | None:
            with self._session_factory() as session:
                chat = self._get_chat_record(session, thread_id)
                return None if chat is None else self._serialize_chat(chat)

        def update_chat_metadata(self, thread_id: str, metadata: dict[str, Any]) -> None:
            with self._session_factory() as session:
                session.execute(
                    update(ChatRecord)
                    .where(ChatRecord.thread_id == thread_id)
                    .values(metadata_json=metadata or {}, updated_at=_utc_now())
                )
                session.commit()

        def update_chat_title(self, thread_id: str, title: str) -> None:
            with self._session_factory() as session:
                session.execute(
                    update(ChatRecord)
                    .where(ChatRecord.thread_id == thread_id)
                    .values(title=title, updated_at=_utc_now())
                )
                session.commit()

        def add_message(
            self,
            thread_id: str,
            role: str,
            content: str,
            reasoning_content: str | None = None,
            metadata: dict[str, Any] | None = None,
        ) -> int:
            with self._session_factory() as session:
                chat = self._get_chat_record(session, thread_id)
                if chat is None:
                    now = _utc_now()
                    chat = ChatRecord(
                        thread_id=thread_id,
                        title="新对话",
                        created_at=now,
                        updated_at=now,
                        metadata_json={},
                    )
                    session.add(chat)
                    session.flush()

                now = _utc_now()
                message = MessageRecord(
                    chat_id=chat.id,
                    role=role,
                    content=content,
                    reasoning_content=reasoning_content,
                    created_at=now,
                    metadata_json=metadata or {},
                )
                session.add(message)
                chat.updated_at = now
                session.commit()
                session.refresh(message)
                return int(message.id)

        def get_messages(self, thread_id: str, limit: int = 50) -> list[dict[str, Any]]:
            limit_value = limit if isinstance(limit, int) and limit > 0 else 50
            with self._session_factory() as session:
                stmt = (
                    select(MessageRecord)
                    .join(ChatRecord, MessageRecord.chat_id == ChatRecord.id)
                    .where(ChatRecord.thread_id == thread_id)
                    .order_by(MessageRecord.created_at.asc(), MessageRecord.id.asc())
                    .limit(limit_value)
                )
                messages = session.execute(stmt).scalars().all()
                return [self._serialize_message(message) for message in messages]

        def get_all_chats(self, limit: int = 50) -> list[dict[str, Any]]:
            limit_value = limit if isinstance(limit, int) and limit > 0 else 50
            with self._session_factory() as session:
                stmt = select(ChatRecord).order_by(desc(ChatRecord.updated_at)).limit(limit_value)
                chats = session.execute(stmt).scalars().all()
                return [self._serialize_chat(chat) for chat in chats]

        def delete_chat(self, thread_id: str) -> None:
            with self._session_factory() as session:
                session.execute(delete(ChatRecord).where(ChatRecord.thread_id == thread_id))
                session.commit()

        def close(self) -> None:
            self._engine.dispose()

        def _get_chat_record(self, session: Session, thread_id: str) -> ChatRecord | None:
            stmt = (
                select(ChatRecord)
                .where(ChatRecord.thread_id == thread_id)
                .order_by(desc(ChatRecord.created_at))
                .limit(1)
            )
            return session.execute(stmt).scalar_one_or_none()

        @staticmethod
        def _serialize_chat(chat: ChatRecord) -> dict[str, Any]:
            return {
                "id": chat.id,
                "thread_id": chat.thread_id,
                "title": chat.title,
                "created_at": chat.created_at.isoformat(),
                "updated_at": chat.updated_at.isoformat(),
                "metadata": chat.metadata_json or {},
            }

        @staticmethod
        def _serialize_message(message: MessageRecord) -> dict[str, Any]:
            return {
                "id": message.id,
                "chat_id": message.chat_id,
                "role": message.role,
                "content": message.content,
                "reasoning_content": message.reasoning_content,
                "created_at": message.created_at.isoformat(),
                "metadata": message.metadata_json or {},
            }

    return PostgresChatStore(database_url)


def ensure_postgres_schema(database_url: str) -> None:
    """Initialize the PostgreSQL chat schema if needed."""
    store = _build_postgres_store(database_url)
    store.close()


_chat_db: BaseChatStore | None = None
_db_lock = threading.Lock()


def create_chat_store(*, database_url: str | None = None) -> BaseChatStore:
    settings = resolve_database_settings(database_url=database_url)
    return _build_postgres_store(settings.database_url)


def get_chat_db() -> BaseChatStore:
    """Get the global chat history storage instance."""
    global _chat_db
    if _chat_db is None:
        with _db_lock:
            if _chat_db is None:
                _chat_db = create_chat_store()
    return _chat_db


def reset_chat_db() -> None:
    """Reset the global chat store for tests or backend reconfiguration."""
    global _chat_db
    with _db_lock:
        if _chat_db is not None:
            _chat_db.close()
        _chat_db = None
