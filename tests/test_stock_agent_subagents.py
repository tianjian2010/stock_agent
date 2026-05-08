import unittest

from agents.stock_agent.subagents import (
    DocumentResearchSubAgent,
    MarketDataSubAgent,
    NewsAnalysisSubAgent,
    SubAgentInput,
    StockScreenerSubAgent,
    SubAgentRegistry,
)
from agents.stock_agent.runtime import AgentTask


class SubAgentRegistryTests(unittest.TestCase):
    def test_registry_resolves_expected_workers(self) -> None:
        registry = SubAgentRegistry()

        self.assertEqual(
            registry.get("document_researcher").worker_name,
            "document_researcher",
        )
        self.assertEqual(registry.get("market_analyst").worker_name, "market_analyst")
        self.assertEqual(registry.get("news_analyst").worker_name, "news_analyst")
        self.assertEqual(registry.get("stock_screener").worker_name, "stock_screener")

    def test_unknown_worker_raises(self) -> None:
        registry = SubAgentRegistry()
        with self.assertRaises(KeyError):
            registry.get("unknown_worker")

    def test_registry_creates_expected_worker_types(self) -> None:
        registry = SubAgentRegistry()
        self.assertIsInstance(registry.get("document_researcher"), DocumentResearchSubAgent)
        self.assertIsInstance(registry.get("market_analyst"), MarketDataSubAgent)
        self.assertIsInstance(registry.get("news_analyst"), NewsAnalysisSubAgent)
        self.assertIsInstance(registry.get("stock_screener"), StockScreenerSubAgent)

    def test_subagent_input_supports_dependency_notes(self) -> None:
        payload = SubAgentInput(
            task=AgentTask(
                task_id="tool_news",
                task_type="tool",
                name="mx_search",
                query="宁德时代 新闻",
                reason="查询新闻",
                worker="news_analyst",
                order=1,
                depends_on=["retrieve_documents"],
            ),
            dependency_notes=["Document findings: 宁德时代深度报告.docx"],
        )
        self.assertEqual(payload.task.depends_on, ["retrieve_documents"])
        self.assertEqual(
            payload.dependency_notes,
            ["Document findings: 宁德时代深度报告.docx"],
        )


if __name__ == "__main__":
    unittest.main()
