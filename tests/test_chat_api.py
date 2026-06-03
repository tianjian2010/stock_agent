import unittest
from unittest.mock import Mock, patch

from agents.stock_agent.agent import StockAgent
from app.api.chat import ChatRequest, _resolve_title


class ChatApiTitleTests(unittest.TestCase):
    def test_resolve_title_generates_title_for_brand_new_stream(self) -> None:
        chat_db = Mock()
        agent = Mock()
        agent.generate_title.return_value = "投研报告数量"
        agent.generate_sidebar_title.return_value = "投研报告数量"

        with patch("app.api.chat.get_chat_db", return_value=chat_db), patch(
            "app.api.chat.get_stock_agent", return_value=agent
        ):
            title = _resolve_title(
                "thread-1",
                ChatRequest(query="现在有多少份投研报告"),
                "现在有多少份投研报告",
            )

        self.assertEqual(title, "投研报告数量")
        chat_db.update_chat_title.assert_called_once_with("thread-1", "投研报告数量")

    def test_resolve_title_regenerates_default_title_for_precreated_thread(self) -> None:
        chat_db = Mock()
        chat_db.get_chat.return_value = {"thread_id": "thread-2", "title": "新对话"}
        agent = Mock()
        agent.generate_title.return_value = "投研报告数量"
        agent.generate_sidebar_title.return_value = "投研报告数量"

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

    def test_resolve_title_regenerates_bad_existing_title(self) -> None:
        chat_db = Mock()
        chat_db.get_chat.return_value = {"thread_id": "thread-bad", "title": "Theuserwantsmet"}
        agent = Mock()
        agent.generate_title.return_value = "旧标题"
        agent.generate_sidebar_title.return_value = "福瑞医科经营边际变化"

        with patch("app.api.chat.get_chat_db", return_value=chat_db), patch(
            "app.api.chat.get_stock_agent", return_value=agent
        ):
            title = _resolve_title(
                "thread-bad",
                ChatRequest(query="福瑞医科最近几篇资料综合看，经营边际变化是什么", thread_id="thread-bad"),
                "福瑞医科最近几篇资料综合看，经营边际变化是什么",
            )

        self.assertEqual(title, "福瑞医科经营边际变化")
        agent.generate_sidebar_title.assert_called_once()
        chat_db.update_chat_title.assert_called_once_with("thread-bad", "福瑞医科经营边际变化")

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
        agent.generate_sidebar_title.assert_not_called()
        chat_db.update_chat_title.assert_not_called()

    def test_resolve_title_prefers_sidebar_title_generator(self) -> None:
        chat_db = Mock()
        agent = Mock()
        agent.generate_title.return_value = "旧标题"
        agent.generate_sidebar_title.return_value = "新标题"

        with patch("app.api.chat.get_chat_db", return_value=chat_db), patch(
            "app.api.chat.get_stock_agent", return_value=agent
        ):
            title = _resolve_title(
                "thread-4",
                ChatRequest(query="福瑞医科最近几篇资料综合看，经营边际变化是什么"),
                "福瑞医科最近几篇资料综合看，经营边际变化是什么",
            )

        self.assertEqual(title, "新标题")
        agent.generate_sidebar_title.assert_called_once()
        agent.generate_title.assert_not_called()
        chat_db.update_chat_title.assert_called_once_with("thread-4", "新标题")

    def test_generate_sidebar_title_rejects_prompt_rule_echo(self) -> None:
        agent = StockAgent.__new__(StockAgent)
        fake_chat = Mock()
        fake_chat.invoke.return_value.content = (
            "用户要求根据问题生成一个会话标题。\n\n要求：\n1. 15个字以内\n2. 保留主体和分析焦点\n3. 不要解释、引号"
        )

        with patch("agents.stock_agent.agent.create_stock_chat", return_value=fake_chat):
            title = StockAgent.generate_sidebar_title(
                agent,
                "福瑞医科最近几篇资料综合看，经营边际变化是什么",
            )

        self.assertEqual(title, "福瑞医科经营边际变化")

    def test_generate_sidebar_title_rejects_english_prompt_echo(self) -> None:
        agent = StockAgent.__new__(StockAgent)
        fake_chat = Mock()
        fake_chat.invoke.return_value.content = "The user wants me to generate a conversation title within 15 characters."

        with patch("agents.stock_agent.agent.create_stock_chat", return_value=fake_chat):
            title = StockAgent.generate_sidebar_title(
                agent,
                "福瑞医科最近几篇资料综合看，经营边际变化是什么",
            )

        self.assertEqual(title, "福瑞医科经营边际变化")


if __name__ == "__main__":
    unittest.main()
