import unittest
from unittest.mock import Mock, patch

from agents.stock_agent.agent import StockAgent
from agents.stock_agent.runtime import build_agent_plan
from services.document_retriever import RetrievalResult


class StockAgentPlannerTests(unittest.TestCase):
    def test_enrich_symbol_lookup_plan_from_memory_uses_recent_codes(self) -> None:
        agent = StockAgent()
        plan = build_agent_plan("\u628a\u4e0a\u9762\u4ee3\u7801\u5bf9\u5e94\u7684\u80a1\u7968\u540d\u79f0\u663e\u793a\u51fa\u6765")

        resolved = agent._enrich_symbol_lookup_plan_from_memory(
            "\u628a\u4e0a\u9762\u4ee3\u7801\u5bf9\u5e94\u7684\u80a1\u7968\u540d\u79f0\u663e\u793a\u51fa\u6765",
            plan,
            [
                {"role": "assistant", "content": "688678 300049 300142"},
                {"role": "user", "content": "...\u4e0a\u9762\u4ee3\u7801..."},
            ],
        )

        self.assertEqual(resolved, ["688678", "300049", "300142"])
        self.assertEqual(plan.planned_tools[0].name, "mx_search")
        self.assertIn("688678 300049 300142", plan.planned_tools[0].query)

    def test_enrich_symbol_lookup_plan_from_memory_skips_when_query_contains_code(self) -> None:
        agent = StockAgent()
        plan = build_agent_plan("688678\u662f\u4ec0\u4e48\u80a1\u7968")
        original_query = plan.planned_tools[0].query

        resolved = agent._enrich_symbol_lookup_plan_from_memory(
            "688678\u662f\u4ec0\u4e48\u80a1\u7968",
            plan,
            [{"role": "assistant", "content": "300049 300142"}],
        )

        self.assertEqual(resolved, [])
        self.assertEqual(plan.planned_tools[0].query, original_query)

    def test_handle_catalog_query_returns_documents_by_date(self) -> None:
        agent = StockAgent()
        query = "5/8日的资料有哪些？"
        plan = build_agent_plan(query)
        with patch.object(
            agent.retriever,
            "list_documents_by_date",
            return_value=[
                {"filename": "福瑞医科0508.txt", "published_at": "2026-05-08"},
                {"filename": "天岳先进0508.txt", "published_at": "2026-05-08"},
            ],
        ):
            answer = agent._handle_catalog_query(query, plan)

        self.assertTrue(answer.startswith("2026-05-08"))
        self.assertIn("0508.txt", answer)
        self.assertIn("(2026-05-08)", answer)

    def test_handle_catalog_query_returns_document_count(self) -> None:
        agent = StockAgent()
        query = "现在有多少个投研报告"
        plan = build_agent_plan(query)
        with patch.object(
            agent.retriever,
            "list_documents",
            return_value=[{"filename": "a"}, {"filename": "b"}],
        ):
            answer = agent._handle_catalog_query(query, plan)

        self.assertIn("2", answer)
        self.assertIn("投研", answer)

    def test_build_agent_plan_routes_latest_document_alias_query(self) -> None:
        plan = build_agent_plan("最近有哪些新研究报？")
        self.assertEqual(plan.direct_answer_mode, "latest_documents")
        self.assertFalse(plan.use_document_search)
        self.assertEqual(plan.intent, "document_catalog_latest")

    def test_select_plan_falls_back_to_rule_plan_when_llm_planner_fails(self) -> None:
        agent = StockAgent()
        initial_plan = build_agent_plan("??????????????????????????")
        with patch.object(agent, "_generate_llm_stages", side_effect=ValueError("bad planner")):
            selected_plan, planner_trace = agent._select_plan(
                "??????????????????????????",
                initial_plan,
            )

        self.assertEqual(selected_plan.planner_source, "rule")
        self.assertTrue(planner_trace)
        self.assertEqual(planner_trace[-1].status, "failed")

    def test_select_plan_reuses_recent_plan_snapshot_when_topic_matches(self) -> None:
        agent = StockAgent()
        query = "宁德时代最新股价"
        initial_plan = build_agent_plan(query)
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
                query,
                initial_plan,
                thread_id="thread-1",
            )

        self.assertEqual(selected_plan.planner_source, "memory_reuse")
        self.assertEqual(len(selected_plan.stages), 1)
        self.assertEqual(planner_trace[0].name, "plan_memory_reuse")
        self.assertEqual(planner_trace[0].status, "completed")

    def test_select_plan_skips_reuse_when_topic_differs(self) -> None:
        agent = StockAgent()
        initial_plan = build_agent_plan("????????????????")
        with patch.object(
            agent.memory_service,
            "get_recent_plan_snapshot",
            return_value={
                "intent": "market_lookup",
                "keywords": ["??????", "???"],
                "stock_codes": [],
                "updated_at": "2099-01-01T00:00:00+00:00",
                "stages": [
                    {
                        "stage_id": "stage_docs",
                        "stage_type": "retrieval",
                        "title": "???????",
                        "goal": "??????",
                        "worker": "document_researcher",
                        "query": "?????? ???",
                        "depends_on": [],
                        "metadata": {},
                    }
                ],
            },
        ), patch.object(agent, "_generate_llm_stages", side_effect=ValueError("bad planner")):
            selected_plan, planner_trace = agent._select_plan(
                "????????????????",
                initial_plan,
                thread_id="thread-1",
            )

        self.assertEqual(selected_plan.planner_source, "rule")
        self.assertEqual(planner_trace[0].name, "plan_memory_reuse")
        self.assertEqual(planner_trace[0].status, "skipped")

    def test_focus_doc_results_prefers_explicit_named_document(self) -> None:
        agent = StockAgent()
        results = [
            RetrievalResult(
                content="福瑞内容",
                score=12,
                metadata={"filename": "福瑞医科0508.txt", "topic": "福瑞医科", "published_at": "2026-05-08"},
            ),
            RetrievalResult(
                content="国芯内容",
                score=11,
                metadata={"filename": "国芯科技0507.txt", "topic": "国芯科技", "published_at": "2026-05-07"},
            ),
        ]

        focused = agent._focus_doc_results("请总结福瑞医科0508.txt", results)

        self.assertEqual(len(focused), 1)
        self.assertEqual(focused[0].metadata["filename"], "福瑞医科0508.txt")

    def test_focus_doc_results_keeps_multi_doc_results_for_broad_query(self) -> None:
        agent = StockAgent()
        results = [
            RetrievalResult(
                content="福瑞内容",
                score=12,
                metadata={"filename": "福瑞医科0508.txt", "topic": "福瑞医科", "published_at": "2026-05-08"},
            ),
            RetrievalResult(
                content="国芯内容",
                score=11,
                metadata={"filename": "国芯科技0507.txt", "topic": "国芯科技", "published_at": "2026-05-07"},
            ),
        ]

        focused = agent._focus_doc_results("帮我总结最近两篇资料的共同点", results)

        self.assertEqual(len(focused), 2)

    def test_focus_doc_results_keeps_same_topic_documents_together(self) -> None:
        agent = StockAgent()
        results = [
            RetrievalResult(
                content="福瑞0508内容",
                score=12,
                metadata={"filename": "福瑞医科0508.txt", "topic": "福瑞医科", "published_at": "2026-05-08"},
            ),
            RetrievalResult(
                content="福瑞0428内容",
                score=11,
                metadata={"filename": "福瑞医科0428.docx", "topic": "福瑞医科", "published_at": "2026-04-28"},
            ),
            RetrievalResult(
                content="国芯内容",
                score=10,
                metadata={"filename": "国芯科技0507.txt", "topic": "国芯科技", "published_at": "2026-05-07"},
            ),
        ]

        focused = agent._focus_doc_results("福瑞医科最近几篇资料综合看", results)

        self.assertEqual(len(focused), 2)
        self.assertTrue(all(item.metadata["topic"] == "福瑞医科" for item in focused))

    def test_focus_doc_results_for_recency_query_includes_latest_topic_document(self) -> None:
        agent = StockAgent()
        results = [
            RetrievalResult(
                content="福瑞0428内容",
                score=11,
                metadata={"filename": "福瑞医科0428.docx", "topic": "福瑞医科", "published_at": "2026-04-28"},
            ),
            RetrievalResult(
                content="福瑞0323内容",
                score=10.5,
                metadata={"filename": "福瑞医科0323.txt", "topic": "福瑞医科", "published_at": "2026-03-23"},
            ),
            RetrievalResult(
                content="国芯内容",
                score=10,
                metadata={"filename": "国芯科技0507.txt", "topic": "国芯科技", "published_at": "2026-05-07"},
            ),
        ]

        agent.retriever = Mock()
        agent.retriever.list_documents.return_value = [
            {"filename": "福瑞医科0428.docx", "topic": "福瑞医科", "published_at": "2026-04-28"},
            {"filename": "福瑞医科0508.txt", "topic": "福瑞医科", "published_at": "2026-05-08"},
            {"filename": "国芯科技0507.txt", "topic": "国芯科技", "published_at": "2026-05-07"},
        ]
        agent.retriever.get_document.return_value = {
            "content": "福瑞0508最新内容",
            "metadata": {"filename": "福瑞医科0508.txt", "topic": "福瑞医科", "published_at": "2026-05-08"},
        }

        focused = agent._focus_doc_results("福瑞医科近期经营边际变化", results)

        self.assertEqual(focused[0].metadata["filename"], "福瑞医科0508.txt")
        self.assertTrue(any(item.metadata["filename"] == "福瑞医科0428.docx" for item in focused))


if __name__ == "__main__":
    unittest.main()
