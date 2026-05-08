import unittest
from unittest.mock import Mock, patch

from app.api.chat import ChatRequest, _resolve_title


class ChatApiTitleTests(unittest.TestCase):
    def test_resolve_title_generates_title_for_brand_new_stream(self) -> None:
        chat_db = Mock()
        agent = Mock()
        agent.generate_title.return_value = "投研报告数量"

        with patch("app.api.chat.get_chat_db", return_value=chat_db), patch(
            "app.api.chat.get_stock_agent", return_value=agent
        ):
            title = _resolve_title("thread-1", ChatRequest(query="现在有多少份投研报告"), "现在有多少份投研报告")

        self.assertEqual(title, "投研报告数量")
        chat_db.update_chat_title.assert_called_once_with("thread-1", "投研报告数量")

    def test_resolve_title_regenerates_default_title_for_precreated_thread(self) -> None:
        chat_db = Mock()
        chat_db.get_chat.return_value = {"thread_id": "thread-2", "title": "新对话"}
        agent = Mock()
        agent.generate_title.return_value = "投研报告数量"

        with patch("app.api.chat.get_chat_db", return_value=chat_db), patch(
            "app.api.chat.get_stock_agent", return_value=agent
        ):
            title = _resolve_title(
                "thread-2",
                ChatRequest(query="现在有多少份投研报告", thread_id="thread-2"),
                "现在有多少份投研报告",
            )

        self.assertEqual(title, "投研报告数量")
        chat_db.update_chat_title.assert_called_once_with("thread-2", "投研报告数量")

    def test_resolve_title_keeps_existing_non_default_title(self) -> None:
        chat_db = Mock()
        chat_db.get_chat.return_value = {"thread_id": "thread-3", "title": "宁德时代分析"}
        agent = Mock()

        with patch("app.api.chat.get_chat_db", return_value=chat_db), patch(
            "app.api.chat.get_stock_agent", return_value=agent
        ):
            title = _resolve_title(
                "thread-3",
                ChatRequest(query="继续", thread_id="thread-3"),
                "继续",
            )

        self.assertEqual(title, "宁德时代分析")
        agent.generate_title.assert_not_called()
        chat_db.update_chat_title.assert_not_called()


if __name__ == "__main__":
    unittest.main()
