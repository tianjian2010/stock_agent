import unittest
from unittest.mock import patch

from agents.stock_agent.agent import StockAgent
from agents.stock_agent.runtime import build_agent_plan


class StockAgentPlannerTests(unittest.TestCase):
    def test_handle_catalog_query_returns_documents_by_date(self) -> None:
        agent = StockAgent()
        plan = build_agent_plan("5/8日的资料有哪一些？")
        with patch.object(
            agent.retriever,
            "list_documents_by_date",
            return_value=[
                {"filename": "福瑞医科0508.txt", "published_at": "2026-05-08"},
                {"filename": "天岳先进0508.txt", "published_at": "2026-05-08"},
            ],
        ):
            answer = agent._handle_catalog_query("5/8日的资料有哪一些？", plan)

        self.assertIn("2026-05-08 的本地投研资料", answer)
        self.assertIn("福瑞医科0508.txt", answer)
        self.assertIn("天岳先进0508.txt", answer)

    def test_handle_catalog_query_returns_document_count(self) -> None:
        agent = StockAgent()
        plan = build_agent_plan("现在有多少个投研报告")
        with patch.object(
            agent.retriever,
            "list_documents",
            return_value=[{"filename": "a"}, {"filename": "b"}],
        ):
            answer = agent._handle_catalog_query("现在有多少个投研报告", plan)

        self.assertEqual(answer, "当前本地共有 2 份投研报告。")

    def test_select_plan_falls_back_to_rule_plan_when_llm_planner_fails(self) -> None:
        agent = StockAgent()
        initial_plan = build_agent_plan("结合创新药研报分析宁德时代最新股价")
        with patch.object(agent, "_generate_llm_stages", side_effect=ValueError("bad planner")):
            selected_plan, planner_trace = agent._select_plan(
                "结合创新药研报分析宁德时代最新股价",
                initial_plan,
            )

        self.assertEqual(selected_plan.planner_source, "rule")
        self.assertTrue(planner_trace)
        self.assertEqual(planner_trace[-1].status, "failed")

    def test_select_plan_reuses_recent_plan_snapshot_when_topic_matches(self) -> None:
        agent = StockAgent()
        initial_plan = build_agent_plan("继续看宁德时代最新股价")
        with patch.object(
            agent.memory_service,
            "get_recent_plan_snapshot",
            return_value={
                "intent": "market_lookup",
                "keywords": ["宁德时代", "最新", "股价"],
                "stock_codes": [],
                "updated_at": "2099-01-01T00:00:00+00:00",
                "stages": [
                    {
                        "stage_id": "stage_docs",
                        "stage_type": "retrieval",
                        "title": "检索资料",
                        "goal": "提取证据",
                        "worker": "document_researcher",
                        "query": "宁德时代 研报",
                        "depends_on": [],
                        "metadata": {},
                    }
                ],
            },
        ):
            selected_plan, planner_trace = agent._select_plan(
                "继续看宁德时代最新股价",
                initial_plan,
                thread_id="thread-1",
            )

        self.assertEqual(selected_plan.planner_source, "memory_reuse")
        self.assertEqual(len(selected_plan.stages), 1)
        self.assertEqual(planner_trace[0].name, "plan_memory_reuse")
        self.assertEqual(planner_trace[0].status, "completed")

    def test_select_plan_skips_reuse_when_topic_differs(self) -> None:
        agent = StockAgent()
        initial_plan = build_agent_plan("筛选创新药低估值股票")
        with patch.object(
            agent.memory_service,
            "get_recent_plan_snapshot",
            return_value={
                "intent": "market_lookup",
                "keywords": ["宁德时代", "股价"],
                "stock_codes": [],
                "updated_at": "2099-01-01T00:00:00+00:00",
                "stages": [
                    {
                        "stage_id": "stage_docs",
                        "stage_type": "retrieval",
                        "title": "检索资料",
                        "goal": "提取证据",
                        "worker": "document_researcher",
                        "query": "宁德时代 研报",
                        "depends_on": [],
                        "metadata": {},
                    }
                ],
            },
        ), patch.object(agent, "_generate_llm_stages", side_effect=ValueError("bad planner")):
            selected_plan, planner_trace = agent._select_plan(
                "筛选创新药低估值股票",
                initial_plan,
                thread_id="thread-1",
            )

        self.assertEqual(selected_plan.planner_source, "rule")
        self.assertEqual(planner_trace[0].name, "plan_memory_reuse")
        self.assertEqual(planner_trace[0].status, "skipped")


if __name__ == "__main__":
    unittest.main()
