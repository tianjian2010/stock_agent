import unittest

from agents.stock_agent.runtime import (
    AgentTask,
    apply_planner_stages,
    build_agent_plan,
    build_execution_tasks,
    build_task_batches,
    choose_recovery_policy,
    evaluate_plan_reuse,
    normalize_stage_payloads,
    summarize_plan,
)


class StockAgentRuntimeTests(unittest.TestCase):
    def test_build_agent_plan_routes_documents_by_date_query(self) -> None:
        plan = build_agent_plan("5/8日的资料有哪一些？")
        self.assertEqual(plan.direct_answer_mode, "documents_by_date")
        self.assertFalse(plan.use_document_search)
        self.assertEqual(plan.intent, "document_catalog_by_date")

    def test_build_agent_plan_routes_latest_document_query(self) -> None:
        plan = build_agent_plan("最近的投研文档有哪些")
        self.assertEqual(plan.direct_answer_mode, "latest_documents")
        self.assertFalse(plan.use_document_search)
        self.assertEqual(plan.intent, "document_catalog_latest")

    def test_build_agent_plan_routes_document_count_query(self) -> None:
        plan = build_agent_plan("现在有多少个投研报告")
        self.assertEqual(plan.direct_answer_mode, "count_documents")
        self.assertFalse(plan.use_document_search)
        self.assertEqual(plan.intent, "document_catalog_count")

    def test_build_agent_plan_routes_screener_query(self) -> None:
        plan = build_agent_plan("帮我筛选低估值的创新药股票")
        self.assertEqual(plan.intent, "stock_screening")
        self.assertEqual(len(plan.planned_tools), 1)
        self.assertEqual(plan.planned_tools[0].name, "mx_select_stock")
        self.assertFalse(plan.use_document_search)

    def test_build_agent_plan_combines_documents_and_market_tools(self) -> None:
        plan = build_agent_plan("结合创新药研报分析宁德时代最新股价")
        self.assertTrue(plan.use_document_search)
        self.assertEqual(plan.intent, "market_augmented_analysis")
        self.assertEqual(plan.planned_tools[0].name, "mx_data_price")
        self.assertEqual(len(plan.stages), 2)
        self.assertEqual(plan.stages[0].stage_type, "retrieval")
        self.assertEqual(plan.stages[1].stage_type, "tool")
        self.assertEqual(plan.stages[1].depends_on, ["stage_research_documents"])
        self.assertEqual(plan.planner_source, "rule")
        self.assertIn("planner=rule", summarize_plan(plan))

    def test_normalize_stage_payloads_accepts_valid_llm_output(self) -> None:
        stages = normalize_stage_payloads(
            [
                {
                    "stage_id": "stage_docs",
                    "stage_type": "retrieval",
                    "title": "检索资料",
                    "goal": "提取本地证据",
                    "worker": "document_researcher",
                    "query": "宁德时代 研报",
                    "depends_on": [],
                    "metadata": {},
                },
                {
                    "stage_id": "stage_news",
                    "stage_type": "tool",
                    "title": "检索新闻",
                    "goal": "核查最新催化",
                    "worker": "news_analyst",
                    "query": "宁德时代 新闻",
                    "depends_on": ["stage_docs"],
                    "metadata": {"tool_name": "mx_search"},
                },
            ]
        )
        self.assertEqual(len(stages), 2)
        self.assertEqual(stages[1].depends_on, ["stage_docs"])

    def test_normalize_stage_payloads_rejects_unknown_dependency(self) -> None:
        with self.assertRaisesRegex(ValueError, "Unknown stage dependency"):
            normalize_stage_payloads(
                [
                    {
                        "stage_id": "stage_news",
                        "stage_type": "tool",
                        "title": "检索新闻",
                        "goal": "核查最新催化",
                        "worker": "news_analyst",
                        "query": "宁德时代 新闻",
                        "depends_on": ["missing_stage"],
                        "metadata": {"tool_name": "mx_search"},
                    }
                ]
            )

    def test_apply_planner_stages_overrides_rule_stages(self) -> None:
        base_plan = build_agent_plan("结合创新药研报分析宁德时代最新股价")
        plan = apply_planner_stages(
            base_plan,
            [
                {
                    "stage_id": "stage_docs",
                    "stage_type": "retrieval",
                    "title": "检索资料",
                    "goal": "提取证据",
                    "worker": "document_researcher",
                    "query": "创新药 研报",
                    "depends_on": [],
                    "metadata": {},
                }
            ],
            planner_source="llm",
        )
        self.assertEqual(plan.planner_source, "llm")
        self.assertEqual(len(plan.stages), 1)
        self.assertEqual(plan.stages[0].stage_id, "stage_docs")

    def test_evaluate_plan_reuse_accepts_matching_topic(self) -> None:
        decision = evaluate_plan_reuse(
            "继续看宁德时代最新股价",
            "market_lookup",
            {
                "intent": "market_lookup",
                "keywords": ["宁德时代", "最新", "股价"],
                "stock_codes": [],
            },
            min_score=0.55,
            is_fresh=True,
        )
        self.assertTrue(decision.should_reuse)
        self.assertGreaterEqual(decision.score, 0.55)

    def test_evaluate_plan_reuse_rejects_mismatched_topic(self) -> None:
        decision = evaluate_plan_reuse(
            "筛选创新药低估值股票",
            "stock_screening",
            {
                "intent": "market_lookup",
                "keywords": ["宁德时代", "股价"],
                "stock_codes": [],
            },
            min_score=0.55,
            is_fresh=True,
        )
        self.assertFalse(decision.should_reuse)

    def test_build_execution_tasks_maps_stages_to_tasks(self) -> None:
        plan = build_agent_plan("结合创新药研报分析宁德时代最新股价")
        tasks = build_execution_tasks(plan, "结合创新药研报分析宁德时代最新股价")

        self.assertEqual(len(tasks), 2)
        self.assertEqual(tasks[0].stage_id, "stage_research_documents")
        self.assertEqual(tasks[1].stage_id, "stage_mx_data_price")
        self.assertEqual(tasks[1].depends_on, ["task_stage_research_documents"])

    def test_build_execution_tasks_routes_screener_query_to_screening_worker(self) -> None:
        plan = build_agent_plan("筛选创新药低估值股票")
        tasks = build_execution_tasks(plan, "筛选创新药低估值股票")

        self.assertEqual(len(tasks), 1)
        self.assertEqual(tasks[0].name, "mx_select_stock")
        self.assertEqual(tasks[0].worker, "stock_screener")

    def test_build_task_batches_splits_dependency_levels(self) -> None:
        tasks = [
            AgentTask(
                task_id="retrieve_documents",
                task_type="retrieval",
                name="document_retrieval",
                query="q",
                reason="r",
                worker="document_researcher",
                order=0,
                stage_id="stage_docs",
            ),
            AgentTask(
                task_id="tool_news",
                task_type="tool",
                name="mx_search",
                query="q",
                reason="r",
                worker="news_analyst",
                order=1,
                depends_on=["retrieve_documents"],
                stage_id="stage_news",
            ),
            AgentTask(
                task_id="tool_price",
                task_type="tool",
                name="mx_data_price",
                query="q",
                reason="r",
                worker="market_analyst",
                order=2,
                depends_on=["retrieve_documents"],
                stage_id="stage_price",
            ),
        ]

        batches = build_task_batches(tasks)

        self.assertEqual(len(batches), 2)
        self.assertEqual(batches[0].task_ids, ["retrieve_documents"])
        self.assertEqual(batches[1].task_ids, ["tool_news", "tool_price"])

    def test_build_task_batches_rejects_cycle(self) -> None:
        tasks = [
            AgentTask(
                task_id="a",
                task_type="tool",
                name="mx_search",
                query="q",
                reason="r",
                worker="news_analyst",
                order=0,
                depends_on=["b"],
                stage_id="stage_a",
            ),
            AgentTask(
                task_id="b",
                task_type="tool",
                name="mx_data_price",
                query="q",
                reason="r",
                worker="market_analyst",
                order=1,
                depends_on=["a"],
                stage_id="stage_b",
            ),
        ]

        with self.assertRaisesRegex(ValueError, "dependency cycle"):
            build_task_batches(tasks)

    def test_choose_recovery_policy_continues_after_retrieval_failure(self) -> None:
        task = AgentTask(
            task_id="task_docs",
            task_type="retrieval",
            name="document_retrieval",
            query="q",
            reason="r",
            worker="document_researcher",
            order=0,
        )

        decision = choose_recovery_policy(task, [], task_success=False)

        self.assertEqual(decision.action, "continue_without_output")
        self.assertTrue(decision.continue_without_output)

    def test_choose_recovery_policy_retries_tool_without_failed_dependencies(self) -> None:
        task = AgentTask(
            task_id="task_news",
            task_type="tool",
            name="mx_search",
            query="q",
            reason="r",
            worker="news_analyst",
            order=1,
            depends_on=["task_docs"],
        )

        decision = choose_recovery_policy(task, ["task_docs"], task_success=False)

        self.assertEqual(decision.action, "retry_without_dependencies")
        self.assertTrue(decision.retry_without_dependencies)


if __name__ == "__main__":
    unittest.main()
