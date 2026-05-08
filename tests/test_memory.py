import unittest
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from unittest.mock import patch

from services.db import create_chat_store
from services.memory import (
    ConversationMemoryService,
    LAST_EXECUTION_METADATA_KEY,
    LAST_PLAN_METADATA_KEY,
    SUMMARY_METADATA_KEY,
    SUMMARY_SOURCE_MESSAGE_ID_METADATA_KEY,
    SUMMARY_UPDATED_AT_METADATA_KEY,
)


class ConversationMemoryTests(unittest.TestCase):
    def test_build_context_messages_includes_summary_and_recent_turns(self) -> None:
        store = create_chat_store()
        thread_id = f"memory-thread-{uuid4()}"
        try:
            store.create_chat(thread_id, "记忆测试")
            store.update_chat_metadata(
                thread_id,
                {SUMMARY_METADATA_KEY: "用户持续关注创新药和宁德时代。"},
            )
            store.add_message(thread_id, "user", "先看一下创新药")
            store.add_message(thread_id, "assistant", "已经检索了创新药资料")
            store.add_message(thread_id, "user", "再看看宁德时代股价")

            memory = ConversationMemoryService(store, history_limit=5)
            context_messages = memory.build_context_messages(
                thread_id,
                "结合前面的内容继续分析",
            )

            self.assertEqual(context_messages[0]["role"], "system")
            self.assertIn("长期记忆摘要", context_messages[0]["content"])
            self.assertEqual(context_messages[-1]["content"], "结合前面的内容继续分析")
            self.assertTrue(any(msg["content"] == "先看一下创新药" for msg in context_messages))
        finally:
            store.delete_chat(thread_id)
            store.close()

    def test_maybe_refresh_summary_persists_result_and_metadata(self) -> None:
        store = create_chat_store()
        thread_id = f"memory-summary-{uuid4()}"
        try:
            store.create_chat(thread_id, "summary")
            for index in range(6):
                role = "user" if index % 2 == 0 else "assistant"
                store.add_message(thread_id, role, f"message-{index}")

            service = ConversationMemoryService(store, history_limit=10)
            with patch.object(
                service,
                "_summarize_messages",
                return_value="记忆摘要已更新",
            ):
                summary = service.maybe_refresh_summary(thread_id)

            self.assertEqual(summary, "记忆摘要已更新")
            chat = store.get_chat(thread_id)
            metadata = chat["metadata"]
            self.assertEqual(metadata[SUMMARY_METADATA_KEY], "记忆摘要已更新")
            self.assertIn(SUMMARY_UPDATED_AT_METADATA_KEY, metadata)
            self.assertIn(SUMMARY_SOURCE_MESSAGE_ID_METADATA_KEY, metadata)
        finally:
            store.delete_chat(thread_id)
            store.close()

    def test_load_memory_marks_stale_summary(self) -> None:
        store = create_chat_store()
        thread_id = f"memory-stale-{uuid4()}"
        try:
            store.create_chat(thread_id, "stale")
            store.update_chat_metadata(
                thread_id,
                {
                    SUMMARY_METADATA_KEY: "旧摘要",
                    SUMMARY_UPDATED_AT_METADATA_KEY: (
                        datetime.now(timezone.utc) - timedelta(hours=48)
                    ).isoformat(),
                },
            )
            service = ConversationMemoryService(store, summary_max_age_hours=24)
            memory = service.load_memory(thread_id)
            self.assertTrue(memory.summary_is_stale)
        finally:
            store.delete_chat(thread_id)
            store.close()

    def test_persist_plan_and_execution_snapshots(self) -> None:
        store = create_chat_store()
        thread_id = f"memory-plan-{uuid4()}"
        try:
            store.create_chat(thread_id, "plan")
            service = ConversationMemoryService(store)
            service.persist_plan_snapshot(
                thread_id,
                {"planner_source": "llm", "stages": [{"stage_id": "stage_docs"}]},
            )
            service.persist_execution_snapshot(
                thread_id,
                {"summary": "执行完成", "tool_names": ["mx_data_price"]},
            )

            chat = store.get_chat(thread_id)
            metadata = chat["metadata"]
            self.assertIn(LAST_PLAN_METADATA_KEY, metadata)
            self.assertIn(LAST_EXECUTION_METADATA_KEY, metadata)
            self.assertEqual(
                metadata[LAST_PLAN_METADATA_KEY]["planner_source"],
                "llm",
            )
            self.assertEqual(
                metadata[LAST_EXECUTION_METADATA_KEY]["summary"],
                "执行完成",
            )
        finally:
            store.delete_chat(thread_id)
            store.close()


if __name__ == "__main__":
    unittest.main()
