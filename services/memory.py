"""Conversation memory helpers for multi-turn stock research threads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.config import (
    MAX_CONVERSATION_HISTORY,
    MEMORY_SUMMARY_BATCH_SIZE,
    MEMORY_SUMMARY_MAX_AGE_HOURS,
    MEMORY_SUMMARY_MAX_CHARS,
    MEMORY_SUMMARY_TRIGGER_MESSAGES,
)
from services.chat_store import BaseChatStore
from services.llm import create_stock_chat

SUMMARY_METADATA_KEY = "memory_summary"
SUMMARY_UPDATED_AT_METADATA_KEY = "memory_summary_updated_at"
SUMMARY_SOURCE_MESSAGE_ID_METADATA_KEY = "memory_summary_source_message_id"
LAST_PLAN_METADATA_KEY = "last_agent_plan"
LAST_PLAN_UPDATED_AT_METADATA_KEY = "last_agent_plan_updated_at"
LAST_EXECUTION_METADATA_KEY = "last_execution_snapshot"
LAST_EXECUTION_UPDATED_AT_METADATA_KEY = "last_execution_updated_at"


@dataclass(slots=True)
class ConversationMemory:
    thread_id: str
    summary: str
    recent_messages: list[dict[str, Any]]
    summary_updated_at: datetime | None = None
    summary_source_message_id: int | None = None
    summary_is_stale: bool = False
    last_agent_plan: dict[str, Any] | None = None
    last_agent_plan_updated_at: datetime | None = None
    last_execution_snapshot: dict[str, Any] | None = None
    last_execution_updated_at: datetime | None = None

    @property
    def has_memory(self) -> bool:
        return bool(
            self.summary.strip()
            or self.recent_messages
            or self.last_agent_plan
            or self.last_execution_snapshot
        )


class ConversationMemoryService:
    """Build and refresh thread-level memory from persisted chat history."""

    def __init__(
        self,
        chat_store: BaseChatStore,
        history_limit: int = MAX_CONVERSATION_HISTORY,
        summary_trigger_messages: int = MEMORY_SUMMARY_TRIGGER_MESSAGES,
        summary_max_age_hours: int = MEMORY_SUMMARY_MAX_AGE_HOURS,
        summary_max_chars: int = MEMORY_SUMMARY_MAX_CHARS,
        summary_batch_size: int = MEMORY_SUMMARY_BATCH_SIZE,
    ):
        self.chat_store = chat_store
        self.history_limit = max(2, history_limit)
        self.summary_trigger_messages = max(2, summary_trigger_messages)
        self.summary_max_age = timedelta(hours=max(1, summary_max_age_hours))
        self.summary_max_chars = max(200, summary_max_chars)
        self.summary_batch_size = max(4, summary_batch_size)

    def load_memory(self, thread_id: str) -> ConversationMemory:
        chat = self.chat_store.get_chat(thread_id) or {}
        metadata = chat.get("metadata") or {}
        summary = str(metadata.get(SUMMARY_METADATA_KEY, "") or "").strip()
        recent_messages = self.chat_store.get_messages(thread_id, limit=self.history_limit)
        summary_updated_at = self._parse_iso_datetime(metadata.get(SUMMARY_UPDATED_AT_METADATA_KEY))
        summary_source_message_id = self._coerce_int(
            metadata.get(SUMMARY_SOURCE_MESSAGE_ID_METADATA_KEY)
        )
        return ConversationMemory(
            thread_id=thread_id,
            summary=summary,
            recent_messages=recent_messages,
            summary_updated_at=summary_updated_at,
            summary_source_message_id=summary_source_message_id,
            summary_is_stale=self._is_summary_stale(summary, summary_updated_at),
            last_agent_plan=self._coerce_dict(metadata.get(LAST_PLAN_METADATA_KEY)),
            last_agent_plan_updated_at=self._parse_iso_datetime(
                metadata.get(LAST_PLAN_UPDATED_AT_METADATA_KEY)
            ),
            last_execution_snapshot=self._coerce_dict(metadata.get(LAST_EXECUTION_METADATA_KEY)),
            last_execution_updated_at=self._parse_iso_datetime(
                metadata.get(LAST_EXECUTION_UPDATED_AT_METADATA_KEY)
            ),
        )

    def build_context_messages(self, thread_id: str, user_query: str) -> list[dict[str, str]]:
        memory = self.load_memory(thread_id)
        context_messages: list[dict[str, str]] = []

        if memory.summary:
            label = "当前会话长期记忆摘要"
            if memory.summary_is_stale:
                label += "（可能已过期）"
            context_messages.append(
                {
                    "role": "system",
                    "content": f"{label}:\n{memory.summary}",
                }
            )

        if memory.last_execution_snapshot:
            execution_summary = str(
                memory.last_execution_snapshot.get("summary", "")
                or memory.last_execution_snapshot.get("answer_excerpt", "")
            ).strip()
            if execution_summary:
                context_messages.append(
                    {
                        "role": "system",
                        "content": f"最近一次执行摘要:\n{execution_summary}",
                    }
                )

        for item in memory.recent_messages:
            content = str(item.get("content", "")).strip()
            if not content:
                continue
            context_messages.append(
                {
                    "role": str(item.get("role", "user")),
                    "content": content,
                }
            )

        context_messages.append({"role": "user", "content": user_query})
        return context_messages

    def maybe_refresh_summary(self, thread_id: str) -> str:
        memory = self.load_memory(thread_id)
        if not memory.recent_messages:
            return memory.summary

        latest_message_id = self._coerce_int(memory.recent_messages[-1].get("id"))
        if latest_message_id is None:
            return memory.summary

        unsummarized_messages = self._count_unsummarized_messages(
            memory.recent_messages,
            memory.summary_source_message_id,
        )
        should_refresh = (
            not memory.summary
            or memory.summary_is_stale
            or unsummarized_messages >= self.summary_trigger_messages
        )
        if not should_refresh:
            return memory.summary

        messages_for_summary = memory.recent_messages[-self.summary_batch_size :]
        summary = self._summarize_messages(messages_for_summary, memory.summary)
        self._persist_summary(thread_id, summary, latest_message_id)
        return summary

    def get_memory_status(self, thread_id: str) -> dict[str, Any]:
        memory = self.load_memory(thread_id)
        return {
            "thread_id": thread_id,
            "recent_message_count": len(memory.recent_messages),
            "has_summary": bool(memory.summary),
            "summary_is_stale": memory.summary_is_stale,
            "summary_updated_at": (
                memory.summary_updated_at.isoformat() if memory.summary_updated_at else None
            ),
            "summary_source_message_id": memory.summary_source_message_id,
            "has_last_plan": bool(memory.last_agent_plan),
            "has_last_execution": bool(memory.last_execution_snapshot),
            "last_plan_updated_at": (
                memory.last_agent_plan_updated_at.isoformat()
                if memory.last_agent_plan_updated_at
                else None
            ),
            "last_execution_updated_at": (
                memory.last_execution_updated_at.isoformat()
                if memory.last_execution_updated_at
                else None
            ),
        }

    def persist_plan_snapshot(self, thread_id: str, plan_data: dict[str, Any]) -> None:
        self._update_chat_metadata(
            thread_id,
            {
                LAST_PLAN_METADATA_KEY: plan_data,
                LAST_PLAN_UPDATED_AT_METADATA_KEY: datetime.now(timezone.utc).isoformat(),
            },
        )

    def persist_execution_snapshot(self, thread_id: str, execution_data: dict[str, Any]) -> None:
        self._update_chat_metadata(
            thread_id,
            {
                LAST_EXECUTION_METADATA_KEY: execution_data,
                LAST_EXECUTION_UPDATED_AT_METADATA_KEY: datetime.now(timezone.utc).isoformat(),
            },
        )

    def get_recent_plan_snapshot(self, thread_id: str) -> dict[str, Any] | None:
        memory = self.load_memory(thread_id)
        return memory.last_agent_plan

    def get_recent_execution_snapshot(self, thread_id: str) -> dict[str, Any] | None:
        memory = self.load_memory(thread_id)
        return memory.last_execution_snapshot

    def _persist_summary(self, thread_id: str, summary: str, source_message_id: int) -> None:
        trimmed_summary = summary.strip()
        if len(trimmed_summary) > self.summary_max_chars:
            trimmed_summary = trimmed_summary[: self.summary_max_chars].rstrip() + "..."

        self._update_chat_metadata(
            thread_id,
            {
                SUMMARY_METADATA_KEY: trimmed_summary,
                SUMMARY_UPDATED_AT_METADATA_KEY: datetime.now(timezone.utc).isoformat(),
                SUMMARY_SOURCE_MESSAGE_ID_METADATA_KEY: source_message_id,
            },
        )

    def _update_chat_metadata(self, thread_id: str, updates: dict[str, Any]) -> None:
        chat = self.chat_store.get_chat(thread_id)
        if chat is None:
            return
        metadata = dict(chat.get("metadata") or {})
        metadata.update(updates)
        self.chat_store.update_chat_metadata(thread_id, metadata)

    @staticmethod
    def _format_messages(messages: list[dict[str, Any]]) -> str:
        lines: list[str] = []
        for item in messages:
            role = str(item.get("role", "user"))
            content = str(item.get("content", "")).strip()
            if content:
                lines.append(f"{role}: {content}")
        return "\n".join(lines)

    def _summarize_messages(self, messages: list[dict[str, Any]], existing_summary: str) -> str:
        try:
            chat = create_stock_chat(temperature=0.2, max_tokens=256, thinking_enabled=False)
            prompt = (
                "请将以下股票研究对话整理成简短会话记忆，保留用户关注标的、"
                "重要观点、已检索资料、已得到的结论，以及下一步待跟进的问题。"
                "输出 4-6 条中文短句，不要使用 Markdown。\n\n"
            )
            if existing_summary:
                prompt += f"已有记忆摘要:\n{existing_summary}\n\n"
            prompt += f"新增对话:\n{self._format_messages(messages)}"
            result = chat.invoke([{"role": "user", "content": prompt}])
            summary = result.content.strip()
            return summary or existing_summary
        except Exception:
            return existing_summary

    @staticmethod
    def _parse_iso_datetime(value: Any) -> datetime | None:
        if not value:
            return None
        try:
            text = str(value)
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_int(value: Any) -> int | None:
        if value is None or value == "":
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_dict(value: Any) -> dict[str, Any] | None:
        return value if isinstance(value, dict) else None

    def _is_summary_stale(self, summary: str, summary_updated_at: datetime | None) -> bool:
        if not summary.strip():
            return False
        if summary_updated_at is None:
            return True
        return datetime.now(timezone.utc) - summary_updated_at > self.summary_max_age

    @staticmethod
    def _count_unsummarized_messages(
        messages: list[dict[str, Any]],
        source_message_id: int | None,
    ) -> int:
        if source_message_id is None:
            return len(messages)
        count = 0
        for item in messages:
            message_id = item.get("id")
            if isinstance(message_id, int) and message_id > source_message_id:
                count += 1
        return count
