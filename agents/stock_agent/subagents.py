"""Specialized worker agents for the stock research coordinator."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from agents.stock_agent.runtime import AgentTask, AgentTraceStep, ToolResult
from services.document_retriever import RetrievalResult, get_document_retriever
from services.market_state_checker import get_market_state_checker
from skills.mx_data import get_mx_data_skill, get_mx_search_skill, get_mx_select_skill


@dataclass(slots=True)
class SubAgentInput:
    task: AgentTask
    dependency_notes: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SubAgentOutput:
    task: AgentTask
    worker: str
    doc_results: list[RetrievalResult] = field(default_factory=list)
    tool_result: ToolResult | None = None
    trace: list[AgentTraceStep] = field(default_factory=list)
    summary_note: str = ""
    success: bool = True
    error_message: str = ""
    recovery_hint: str = ""
    degraded: bool = False


class BaseSubAgent:
    worker_name = "base_worker"

    def run(self, payload: SubAgentInput) -> SubAgentOutput:
        raise NotImplementedError

    def _build_failure_output(
        self,
        payload: SubAgentInput,
        *,
        detail: str,
        error_message: str,
        recovery_hint: str,
        tool_result: ToolResult | None = None,
    ) -> SubAgentOutput:
        return SubAgentOutput(
            task=payload.task,
            worker=self.worker_name,
            tool_result=tool_result,
            trace=[
                AgentTraceStep(
                    name=f"subagent:{self.worker_name}",
                    status="failed",
                    detail=detail,
                    data={
                        "task_id": payload.task.task_id,
                        "worker": self.worker_name,
                        "dependency_notes": payload.dependency_notes,
                        "error_message": error_message,
                        "recovery_hint": recovery_hint,
                        "tool_result": asdict(tool_result) if tool_result else {},
                    },
                )
            ],
            summary_note=f"{payload.task.name} failed.",
            success=False,
            error_message=error_message,
            recovery_hint=recovery_hint,
            degraded=True,
        )


class DocumentResearchSubAgent(BaseSubAgent):
    worker_name = "document_researcher"

    def __init__(self) -> None:
        self.retriever = get_document_retriever()

    def run(self, payload: SubAgentInput) -> SubAgentOutput:
        task = payload.task
        try:
            doc_results = self.retriever.search(task.query)
        except Exception as exc:
            return self._build_failure_output(
                payload,
                detail="Document worker failed during retrieval.",
                error_message=str(exc),
                recovery_hint="Continue with market tools or retry document indexing.",
            )

        filenames = [item.metadata.get("filename", "") for item in doc_results]
        trace = [
            AgentTraceStep(
                name=f"subagent:{self.worker_name}",
                status="completed",
                detail=f"Document worker retrieved {len(doc_results)} chunks.",
                data={
                    "task_id": task.task_id,
                    "worker": self.worker_name,
                    "citation_filenames": filenames,
                },
            )
        ]
        summary_note = (
            f"Document findings: {', '.join(name for name in filenames[:3] if name)}"
            if filenames
            else "Document findings: no relevant local documents found."
        )
        return SubAgentOutput(
            task=task,
            worker=self.worker_name,
            doc_results=doc_results,
            trace=trace,
            summary_note=summary_note,
        )


class MarketDataSubAgent(BaseSubAgent):
    worker_name = "market_analyst"

    def __init__(self) -> None:
        self.skill = get_mx_data_skill()

    def run(self, payload: SubAgentInput) -> SubAgentOutput:
        task = payload.task
        request = self._augment_request(task.query, payload.dependency_notes)
        try:
            payload_data = self.skill.query(request)
        except Exception as exc:
            return self._build_failure_output(
                payload,
                detail=f"Market worker failed while executing {task.name}.",
                error_message=str(exc),
                recovery_hint="Continue with available document evidence or retry the market tool.",
                tool_result=ToolResult(
                    name=task.name,
                    request=request,
                    content=f"Tool execution failed: {exc}",
                    reason=task.reason,
                    success=False,
                    worker=self.worker_name,
                    degraded=True,
                    error_message=str(exc),
                ),
            )

        tool_result = ToolResult(
            name=task.name,
            request=request,
            content=self.skill.format_result(payload_data),
            reason=task.reason,
            success="error" not in payload_data,
            worker=self.worker_name,
            degraded="error" in payload_data,
            error_message="" if "error" not in payload_data else self.skill.format_result(payload_data),
        )
        trace = [
            AgentTraceStep(
                name=f"subagent:{self.worker_name}",
                status="completed" if tool_result.success else "failed",
                detail=f"Market worker executed {task.name}.",
                data={
                    "task_id": task.task_id,
                    "worker": self.worker_name,
                    "dependency_notes": payload.dependency_notes,
                    "tool_result": asdict(tool_result),
                },
            )
        ]
        success = tool_result.success
        return SubAgentOutput(
            task=task,
            worker=self.worker_name,
            tool_result=tool_result,
            trace=trace,
            summary_note=(
                f"Market findings from {task.name}."
                if success
                else f"Market findings unavailable for {task.name}."
            ),
            success=success,
            error_message="" if success else tool_result.content,
            recovery_hint=(
                ""
                if success
                else "Continue with other evidence or retry the market lookup."
            ),
            degraded=not success,
        )

    @staticmethod
    def _augment_request(query: str, dependency_notes: list[str]) -> str:
        if not dependency_notes:
            return query
        return f"{query}\n\nUpstream notes:\n" + "\n".join(f"- {note}" for note in dependency_notes)


class NewsAnalysisSubAgent(BaseSubAgent):
    worker_name = "news_analyst"

    def __init__(self) -> None:
        self.skill = get_mx_search_skill()

    def run(self, payload: SubAgentInput) -> SubAgentOutput:
        task = payload.task
        request = self._augment_request(task.query, payload.dependency_notes)
        try:
            payload_data = self.skill.search(request)
        except Exception as exc:
            return self._build_failure_output(
                payload,
                detail="News worker failed during catalyst lookup.",
                error_message=str(exc),
                recovery_hint="Continue with document evidence or retry the news tool.",
                tool_result=ToolResult(
                    name=task.name,
                    request=request,
                    content=f"Tool execution failed: {exc}",
                    reason=task.reason,
                    success=False,
                    worker=self.worker_name,
                    degraded=True,
                    error_message=str(exc),
                ),
            )

        tool_result = ToolResult(
            name=task.name,
            request=request,
            content=self.skill.format_result(payload_data),
            reason=task.reason,
            success="error" not in payload_data,
            worker=self.worker_name,
            degraded="error" in payload_data,
            error_message="" if "error" not in payload_data else self.skill.format_result(payload_data),
        )
        trace = [
            AgentTraceStep(
                name=f"subagent:{self.worker_name}",
                status="completed" if tool_result.success else "failed",
                detail="News worker completed news and catalyst lookup.",
                data={
                    "task_id": task.task_id,
                    "worker": self.worker_name,
                    "dependency_notes": payload.dependency_notes,
                    "tool_result": asdict(tool_result),
                },
            )
        ]
        success = tool_result.success
        return SubAgentOutput(
            task=task,
            worker=self.worker_name,
            tool_result=tool_result,
            trace=trace,
            summary_note=(
                "News findings collected."
                if success
                else "News findings unavailable."
            ),
            success=success,
            error_message="" if success else tool_result.content,
            recovery_hint=(
                ""
                if success
                else "Continue with other evidence or retry the news lookup."
            ),
            degraded=not success,
        )

    @staticmethod
    def _augment_request(query: str, dependency_notes: list[str]) -> str:
        if not dependency_notes:
            return query
        return f"{query}\n\nUse these upstream notes if relevant:\n" + "\n".join(
            f"- {note}" for note in dependency_notes
        )


class StockScreenerSubAgent(BaseSubAgent):
    worker_name = "stock_screener"

    def __init__(self) -> None:
        self.skill = get_mx_select_skill()

    def run(self, payload: SubAgentInput) -> SubAgentOutput:
        task = payload.task
        request = self._augment_request(task.query, payload.dependency_notes)
        try:
            payload_data = self.skill.select(request)
        except Exception as exc:
            return self._build_failure_output(
                payload,
                detail="Screening worker failed during candidate filtering.",
                error_message=str(exc),
                recovery_hint="Continue with other evidence or retry the screening tool.",
                tool_result=ToolResult(
                    name=task.name,
                    request=request,
                    content=f"Tool execution failed: {exc}",
                    reason=task.reason,
                    success=False,
                    worker=self.worker_name,
                    degraded=True,
                    error_message=str(exc),
                ),
            )

        tool_result = ToolResult(
            name=task.name,
            request=request,
            content=self.skill.format_result(payload_data),
            reason=task.reason,
            success="error" not in payload_data,
            worker=self.worker_name,
            degraded="error" in payload_data,
            error_message="" if "error" not in payload_data else self.skill.format_result(payload_data),
        )
        trace = [
            AgentTraceStep(
                name=f"subagent:{self.worker_name}",
                status="completed" if tool_result.success else "failed",
                detail="Screening worker completed candidate stock filtering.",
                data={
                    "task_id": task.task_id,
                    "worker": self.worker_name,
                    "dependency_notes": payload.dependency_notes,
                    "tool_result": asdict(tool_result),
                },
            )
        ]
        success = tool_result.success
        return SubAgentOutput(
            task=task,
            worker=self.worker_name,
            tool_result=tool_result,
            trace=trace,
            summary_note=(
                "Screening findings collected."
                if success
                else "Screening findings unavailable."
            ),
            success=success,
            error_message="" if success else tool_result.content,
            recovery_hint=(
                ""
                if success
                else "Continue with other evidence or retry the screening tool."
            ),
            degraded=not success,
        )

    @staticmethod
    def _augment_request(query: str, dependency_notes: list[str]) -> str:
        if not dependency_notes:
            return query
        return f"{query}\n\nUse these upstream notes if relevant:\n" + "\n".join(
            f"- {note}" for note in dependency_notes
        )


class MarketStateSubAgent(BaseSubAgent):
    """Agent that checks breakout, trend, and technical state."""

    worker_name = "market_state_checker"

    _HISTORICAL_HIGH_TERMS = ("历史新高", "历史最高", "史上最高", "历史高位", "上市以来最高")

    def __init__(self) -> None:
        self.checker = get_market_state_checker()

    def run(self, payload: SubAgentInput) -> SubAgentOutput:
        task = payload.task
        query = task.query
        dependency_notes = payload.dependency_notes
        check_type = str(task.metadata.get("check_type", "")) if task.metadata else ""

        try:
            stock_code = self._extract_stock_code(query)
            if not stock_code:
                stock_code = query.strip()

            is_historical = any(term in query for term in self._HISTORICAL_HIGH_TERMS)

            if "trend" in check_type or "趋势" in query or "走势" in query:
                trend = self.checker.check_trend(stock_code)
                formatted = self.checker.format_trend_result(trend)
            else:
                breakout = self.checker.check_breakout(stock_code, extended=is_historical)
                formatted = self.checker.format_breakout_result(breakout)

            tool_result = ToolResult(
                name=task.name,
                request=query,
                content=formatted,
                reason=task.reason,
                success=True,
                worker=self.worker_name,
            )
            trace = [
                AgentTraceStep(
                    name=f"subagent:{self.worker_name}",
                    status="completed",
                    detail=f"Market state checked: {stock_code}",
                    data={
                        "task_id": task.task_id,
                        "worker": self.worker_name,
                        "check_type": check_type,
                    },
                )
            ]
            return SubAgentOutput(
                task=task,
                worker=self.worker_name,
                tool_result=tool_result,
                trace=trace,
                summary_note=f"Market state analysis for {stock_code}.",
            )
        except Exception as exc:
            return self._build_failure_output(
                payload,
                detail="Market state check failed.",
                error_message=str(exc),
                recovery_hint="Continue with document evidence or retry market lookup.",
                tool_result=ToolResult(
                    name=task.name,
                    request=query,
                    content=f"Market state check failed: {exc}",
                    reason=task.reason,
                    success=False,
                    worker=self.worker_name,
                    degraded=True,
                    error_message=str(exc),
                ),
            )

    @staticmethod
    def _extract_stock_code(query: str) -> str:
        import re
        m = re.search(r"(?<!\d)(\d{6})(?!\d)", query)
        if m:
            return m.group(1)
        return ""


class SubAgentRegistry:
    def __init__(self) -> None:
        self._agents: dict[str, BaseSubAgent] = {
            "document_researcher": DocumentResearchSubAgent(),
            "market_analyst": MarketDataSubAgent(),
            "news_analyst": NewsAnalysisSubAgent(),
            "stock_screener": StockScreenerSubAgent(),
            "market_state_checker": MarketStateSubAgent(),
        }

    def get(self, worker: str) -> BaseSubAgent:
        if worker not in self._agents:
            raise KeyError(f"Unknown sub-agent worker: {worker}")
        return self._agents[worker]
