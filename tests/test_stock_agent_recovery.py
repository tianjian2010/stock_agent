import unittest

from agents.stock_agent.agent import StockAgent
from agents.stock_agent.runtime import AgentTask, TaskBatch, ToolResult
from agents.stock_agent.subagents import BaseSubAgent, SubAgentInput, SubAgentOutput


class _FailingDocumentWorker(BaseSubAgent):
    worker_name = "document_researcher"

    def run(self, payload: SubAgentInput) -> SubAgentOutput:
        raise RuntimeError("document retrieval failed")


class _RetryingNewsWorker(BaseSubAgent):
    worker_name = "news_analyst"

    def __init__(self) -> None:
        self.requests: list[list[str]] = []

    def run(self, payload: SubAgentInput) -> SubAgentOutput:
        self.requests.append(list(payload.dependency_notes))
        if payload.dependency_notes:
            return SubAgentOutput(
                task=payload.task,
                worker=self.worker_name,
                summary_note="news failed with upstream notes",
                success=False,
                error_message="dependency shaped request failed",
                recovery_hint="retry without dependencies",
                degraded=True,
            )
        return SubAgentOutput(
            task=payload.task,
            worker=self.worker_name,
            summary_note="news succeeded without upstream notes",
            success=True,
        )


class _StableMarketWorker(BaseSubAgent):
    worker_name = "market_analyst"

    def run(self, payload: SubAgentInput) -> SubAgentOutput:
        return SubAgentOutput(
            task=payload.task,
            worker=self.worker_name,
            summary_note="market success",
            success=True,
            tool_result=ToolResult(
                name=payload.task.name,
                request=payload.task.query,
                content="price ok",
                reason=payload.task.reason,
                success=True,
                worker=self.worker_name,
            ),
        )


class StockAgentRecoveryTests(unittest.TestCase):
    def test_execute_task_batch_retries_without_failed_dependencies(self) -> None:
        agent = StockAgent()
        retrying_worker = _RetryingNewsWorker()
        agent.subagent_registry._agents["news_analyst"] = retrying_worker

        completed_outputs = {
            "task_docs": SubAgentOutput(
                task=AgentTask(
                    task_id="task_docs",
                    task_type="retrieval",
                    name="document_retrieval",
                    query="docs",
                    reason="research",
                    worker="document_researcher",
                    order=0,
                ),
                worker="document_researcher",
                summary_note="document stage failed",
                success=False,
                error_message="document retrieval failed",
                recovery_hint="continue without docs",
                degraded=True,
            )
        }
        task = AgentTask(
            task_id="task_news",
            task_type="tool",
            name="mx_search",
            query="news",
            reason="news lookup",
            worker="news_analyst",
            order=1,
            depends_on=["task_docs"],
        )

        output = agent._run_subagent_task(task, completed_outputs)

        self.assertTrue(output.success)
        self.assertEqual(retrying_worker.requests, [["document stage failed"], []])
        self.assertEqual(output.trace[0].name, "retry_task_without_dependencies")

    def test_dispatch_task_graph_preserves_independent_success_after_retrieval_failure(self) -> None:
        agent = StockAgent()
        agent.subagent_registry._agents["document_researcher"] = _FailingDocumentWorker()
        agent.subagent_registry._agents["market_analyst"] = _StableMarketWorker()

        retrieval_task = AgentTask(
            task_id="task_docs",
            task_type="retrieval",
            name="document_retrieval",
            query="docs",
            reason="research",
            worker="document_researcher",
            order=0,
        )
        market_task = AgentTask(
            task_id="task_price",
            task_type="tool",
            name="mx_data_price",
            query="price",
            reason="market lookup",
            worker="market_analyst",
            order=1,
            depends_on=["task_docs"],
        )
        batches = [
            TaskBatch(batch_id=0, task_ids=["task_docs"], tasks=[retrieval_task]),
            TaskBatch(batch_id=1, task_ids=["task_price"], tasks=[market_task]),
        ]

        result = agent._dispatch_task_graph(batches)

        self.assertEqual(len(result["tool_results"]), 1)
        self.assertTrue(result["tool_results"][0].success)
        self.assertEqual(len(result["outputs"]), 2)
        trace_names = [step.name for step in result["trace"]]
        self.assertIn("recover_stage_failure", trace_names)

    def test_build_recovery_summary_marks_recovered_tool_stage(self) -> None:
        agent = StockAgent()
        tool_result = ToolResult(
            name="mx_search",
            request="news",
            content="ok",
            reason="lookup",
            success=True,
            worker="news_analyst",
            degraded=True,
            recovered=True,
            recovery_action="retry_without_dependencies",
        )
        outputs = [
            SubAgentOutput(
                task=AgentTask(
                    task_id="task_news",
                    task_type="tool",
                    name="mx_search",
                    query="news",
                    reason="lookup",
                    worker="news_analyst",
                    order=1,
                    stage_id="stage_news",
                ),
                worker="news_analyst",
                summary_note="news recovered",
                success=True,
                degraded=True,
            )
        ]

        summary = agent._build_recovery_summary(outputs, [tool_result])

        self.assertTrue(summary["has_recovery"])
        self.assertEqual(summary["recovered_count"], 1)
        self.assertEqual(summary["stages"][0]["status"], "recovered")
        self.assertTrue(summary["recommended_actions"])

    def test_append_recovery_note_adds_user_visible_suffix(self) -> None:
        agent = StockAgent()

        answer = agent._append_recovery_note(
            "主体回答",
            {
                "has_recovery": True,
                "recovered_count": 1,
                "degraded_count": 1,
                "failed_count": 0,
                "recommended_actions": ["稍后重试。", "改成更具体的问法。"],
                "stages": [],
            },
        )

        self.assertIn("执行说明", answer)
        self.assertIn("1 个阶段已降级恢复", answer)
        self.assertIn("建议动作", answer)

    def test_inline_citation_labels_adds_default_label_to_uncited_paragraph(self) -> None:
        agent = StockAgent()

        answer = "第一段结论。\n\n第二段展开说明。"
        citations = [
            {"filename": "福瑞医科0508.txt", "published_at": "2026-05-08", "chunk_id": 0, "total_chunks": 3}
        ]

        updated = agent._inline_citation_labels(answer, citations)

        self.assertIn("第一段结论。[资料1]", updated)
        self.assertIn("第二段展开说明。[资料1]", updated)

    def test_inline_citation_labels_keeps_existing_inline_reference(self) -> None:
        agent = StockAgent()

        answer = "第一段结论[资料2]。\n\n第二段展开说明。"
        citations = [
            {"filename": "福瑞医科0508.txt", "published_at": "2026-05-08", "chunk_id": 0, "total_chunks": 3},
            {"filename": "国芯科技0507.txt", "published_at": "2026-05-07", "chunk_id": 1, "total_chunks": 4},
        ]

        updated = agent._inline_citation_labels(answer, citations)

        self.assertEqual(updated.count("[资料2]"), 1)
        self.assertIn("第二段展开说明。[资料1]", updated)

    def test_inline_citation_labels_prefers_best_matching_document(self) -> None:
        agent = StockAgent()

        answer = "国芯的抗量子金融POS机已经量产出货。"
        citations = [
            {
                "filename": "福瑞医科0508.txt",
                "topic": "福瑞医科",
                "published_at": "2026-05-08",
                "chunk_id": 0,
                "total_chunks": 3,
                "snippet": "Echosens中国分公司调研纪要反馈，国内公立医院招投标中标数量增长40%。",
            },
            {
                "filename": "国芯科技0507.txt",
                "topic": "国芯科技",
                "published_at": "2026-05-07",
                "chunk_id": 1,
                "total_chunks": 4,
                "snippet": "国芯科技实现抗量子金融POS机芯片CUni360SQ-ZX量产出货。",
            },
        ]

        updated = agent._inline_citation_labels(answer, citations)

        self.assertIn("[资料2]", updated)

    def test_build_evidence_scope_context_for_single_topic(self) -> None:
        agent = StockAgent()
        citations = [
            {"filename": "福瑞医科0508.txt", "topic": "福瑞医科"},
            {"filename": "福瑞医科0428.docx", "topic": "福瑞医科"},
        ]

        context = agent._build_evidence_scope_context(citations)

        self.assertIn("同一主题的多篇文档", context)
        self.assertIn("福瑞医科", context)

    def test_build_evidence_scope_context_for_multi_topic(self) -> None:
        agent = StockAgent()
        citations = [
            {"filename": "福瑞医科0508.txt", "topic": "福瑞医科"},
            {"filename": "国芯科技0507.txt", "topic": "国芯科技"},
        ]

        context = agent._build_evidence_scope_context(citations)

        self.assertIn("多个不同主题", context)
        self.assertIn("按主题分组说明", context)

    def test_filter_citations_by_answer_usage_removes_unused_items(self) -> None:
        agent = StockAgent()
        citations = [
            {"filename": "福瑞医科0508.txt", "citation_index": 1},
            {"filename": "福瑞医科0428.docx", "citation_index": 2},
            {"filename": "福瑞医科0420.txt", "citation_index": 3},
        ]

        filtered = agent._filter_citations_by_answer_usage(
            "结论来自[资料1]，补充说明见[资料3]。",
            citations,
        )

        self.assertEqual([item["filename"] for item in filtered], ["福瑞医科0508.txt", "福瑞医科0420.txt"])

    def test_build_citation_note_preserves_original_citation_index(self) -> None:
        agent = StockAgent()
        note = agent._build_citation_note(
            [
                {"filename": "福瑞医科0508.txt", "citation_index": 1},
                {"filename": "福瑞医科0420.txt", "citation_index": 3},
            ]
        )

        self.assertIn("[资料1] 福瑞医科0508.txt", note)
        self.assertIn("[资料3] 福瑞医科0420.txt", note)

    def test_inline_citation_labels_skips_heading_like_blocks(self) -> None:
        agent = StockAgent()
        answer = "一、国内设备销售\n\n招投标数量同比高增长。"
        citations = [{"filename": "福瑞医科0508.txt", "citation_index": 1}]

        updated = agent._inline_citation_labels(answer, citations)

        self.assertIn("一、国内设备销售", updated)
        self.assertNotIn("一、国内设备销售[资料1]", updated)
        self.assertIn("招投标数量同比高增长。[资料1]", updated)

    def test_normalize_inline_citation_format_wraps_plain_labels(self) -> None:
        agent = StockAgent()

        updated = agent._normalize_inline_citation_format("核心结论 资料1，补充见资料3。")

        self.assertEqual(updated, "核心结论 [资料1]，补充见[资料3]。")

    def test_rewrite_inference_citation_style_moves_citations_into_prefix(self) -> None:
        agent = StockAgent()

        updated = agent._rewrite_inference_citation_style("判断： 这一趋势会持续。 [资料1] [资料3]")

        self.assertEqual(updated, "判断（基于[资料1]、[资料3]）：这一趋势会持续。")

    def test_strip_heading_trailing_citations_removes_heading_suffix_only(self) -> None:
        agent = StockAgent()
        answer = "一、国内设备销售 [资料1]\n招投标数量同比高增长。[资料1]"

        updated = agent._strip_heading_trailing_citations(answer)

        self.assertIn("一、国内设备销售", updated)
        self.assertNotIn("一、国内设备销售 [资料1]", updated)
        self.assertIn("招投标数量同比高增长。[资料1]", updated)

    def test_realistic_stock_answer_post_processing_removes_heading_suffixes(self) -> None:
        agent = StockAgent()
        answer = """福瑞医科近期经营边际变化综合分析 [资料3]
一、核心结论
短期财务指标承压，但业务基本面出现积极边际改善。 [资料1]

二、收入端：增速回落但订单质量显著提升 [资料1]
财务数据表面平淡：一季报归母净利润3200万元、同比增长11%，投研部评价为“较差数据”[资料2]。
判断：短期报表增速放缓主要受会计处理影响。 [资料2]
"""

        updated = agent._normalize_inline_citation_format(answer)
        updated = agent._strip_heading_trailing_citations(updated)
        updated = agent._rewrite_inference_citation_style(updated)

        self.assertNotIn("综合分析 [资料3]", updated)
        self.assertNotIn("提升 [资料1]", updated)
        self.assertIn("短期财务指标承压，但业务基本面出现积极边际改善。 [资料1]", updated)
        self.assertIn("判断（基于[资料2]）：短期报表增速放缓主要受会计处理影响。", updated)


if __name__ == "__main__":
    unittest.main()
