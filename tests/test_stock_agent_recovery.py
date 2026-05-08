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


if __name__ == "__main__":
    unittest.main()
