"""Stock agent orchestration layer."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from agents.stock_agent.runtime import (
    AgentPlan,
    AgentRunResult,
    AgentTask,
    AgentTraceStep,
    RecoveryDecision,
    TaskBatch,
    ToolResult,
    apply_planner_stages,
    build_agent_plan,
    build_execution_tasks,
    build_task_batches,
    choose_recovery_policy,
    evaluate_plan_reuse,
    extract_plan_topic_signals,
    summarize_plan,
)
from agents.stock_agent.subagents import SubAgentInput, SubAgentOutput, SubAgentRegistry
from app.config import ENABLE_LLM_PLANNER, PLAN_REUSE_MAX_AGE_HOURS, PLAN_REUSE_MIN_SCORE
from services.db import get_chat_db
from services.document_retriever import RetrievalResult, extract_query_keywords, get_document_retriever
from services.llm import create_stock_chat
from services.memory import ConversationMemoryService

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """
你是一个面向 A 股投研场景的研究型 AI Agent。
工作原则：
1. 优先使用本地投研资料理解背景、逻辑和观点。
2. 在需要实时事实时，再调用行情、资讯或选股工具补充证据。
3. 回答必须简洁、可信、可追溯。

回答要求：
- 默认使用中文。
- 优先引用本地资料，引用格式使用 [资料1]、[资料2]。
- 如果使用了外部行情或资讯，要明确标注为“实时数据/资讯”。
- 如果证据不足，直接说明不确定点，不要编造。
""".strip()

PLANNER_PROMPT = """
你是一个 A 股投研执行计划器。请基于用户问题，输出一个 JSON 数组，每个元素代表一个执行阶段。

允许 worker:
- document_researcher
- market_analyst
- news_analyst
- stock_screener

允许 stage_type:
- retrieval
- tool

要求：
1. 只输出 JSON，不要解释。
2. 每个阶段必须包含: stage_id, stage_type, title, goal, worker, query, depends_on, metadata
3. depends_on 必须引用前面阶段的 stage_id
4. 如果问题需要先看本地研报再查实时信息，请先放 retrieval 阶段
5. 如果只是纯新闻或纯选股，可直接给 tool 阶段
6. metadata 可以为空对象，若是工具阶段可放 tool_name
""".strip()

FILENAME_PATTERN = re.compile(
    r"([\w\u4e00-\u9fff&-]+\.(?:txt|docx|pdf|xlsx|xls|csv|mp3|wav|m4a|aac|flac|ogg|mp4))"
)


def _extract_answer(text: str) -> str:
    if "<think>" in text and "</think>" in text:
        _, answer = text.split("</think>", 1)
        return answer.strip()
    return text.strip()


def _status_label(success: bool, degraded: bool, recovered: bool) -> str:
    if success and recovered:
        return "recovered"
    if success and degraded:
        return "degraded"
    if success:
        return "ok"
    return "failed"


@dataclass(slots=True)
class PreparedAnswerContext:
    query: str
    thread_id: str | None
    plan: AgentPlan
    trace: list[AgentTraceStep]
    memory_messages: list[dict[str, str]]
    memory_status: dict[str, Any]
    doc_context: str
    tool_context: str
    recovery_context: str
    citations: list[dict[str, Any]]
    tool_results: list[ToolResult]
    recovery: dict[str, Any]
    direct_answer: str | None = None


ProgressCallback = Callable[[str, dict[str, Any]], None]


class StockAgent:
    """Coordinator agent for local research docs and specialized worker agents."""

    def __init__(self) -> None:
        self.retriever = get_document_retriever()
        self.chat_store = get_chat_db()
        self.memory_service = ConversationMemoryService(self.chat_store)
        self.subagent_registry = SubAgentRegistry()

    def generate_title(self, user_message: str) -> str:
        fallback = user_message.strip().replace("\n", " ")[:15] or "新对话"
        try:
            chat = create_stock_chat(temperature=0.2, max_tokens=64, thinking_enabled=False)
            prompt = f"请只返回一个不超过 15 个字的中文标题，不要解释：{user_message}"
            response = chat.invoke([{"role": "user", "content": prompt}])
            title = _extract_answer(response.content).strip().strip("\"'")[:15]
            return title or fallback
        except Exception as exc:
            logger.warning("Title generation fallback: %s", exc)
            return fallback

    def run(self, query: str, thread_id: str | None = None) -> AgentRunResult:
        active_thread_id = thread_id or ""
        base_plan = build_agent_plan(query)
        plan, planner_trace = self._select_plan(query, base_plan, thread_id=active_thread_id)
        trace: list[AgentTraceStep] = [
            AgentTraceStep(
                name="plan_query",
                status="completed",
                detail=summarize_plan(plan),
                data={
                    "plan": asdict(plan),
                    "stage_count": len(plan.stages),
                    "planner_source": plan.planner_source,
                },
            )
        ]
        trace.extend(planner_trace)

        if plan.stages:
            trace.append(
                AgentTraceStep(
                    name="build_plan_stages",
                    status="completed",
                    detail=f"Planner built {len(plan.stages)} explicit stage(s).",
                    data={"stages": [asdict(stage) for stage in plan.stages]},
                )
            )

        memory_messages: list[dict[str, str]] = []
        memory_status: dict[str, Any] = {}
        if active_thread_id:
            memory = self.memory_service.load_memory(active_thread_id)
            memory_messages = self.memory_service.build_context_messages(active_thread_id, query)
            memory_status = self.memory_service.get_memory_status(active_thread_id)
            prior_message_count = max(0, len(memory_messages) - 1 - (1 if memory.summary else 0))
            trace.append(
                AgentTraceStep(
                    name="load_memory",
                    status="completed" if memory.has_memory else "skipped",
                    detail=(
                        f"Loaded {prior_message_count} prior context messages and "
                        f"{'an existing summary' if memory.summary else 'no summary'}."
                    ),
                    data=memory_status,
                )
            )

        self.retriever.index_documents()

        direct_answer = self._handle_catalog_query(query, plan)
        if direct_answer is not None:
            trace.append(
                AgentTraceStep(
                    name="direct_answer",
                    status="completed",
                    detail=f"Direct mode: {plan.direct_answer_mode}",
                )
            )
            if active_thread_id:
                self._persist_plan_memory(active_thread_id, query, plan)
                self._persist_execution_memory(
                    active_thread_id,
                    plan=plan,
                    query=query,
                    answer=direct_answer,
                    tool_results=[],
                    citations=[],
                    trace=trace,
                )
            return AgentRunResult(
                answer=direct_answer,
                citations=[],
                tool_results=[],
                plan=plan,
                trace=trace,
                recovery={},
            )

        tasks = build_execution_tasks(plan, query)
        batches = build_task_batches(tasks)
        trace.append(
            AgentTraceStep(
                name="decompose_tasks",
                status="completed" if tasks else "skipped",
                detail=(
                    f"Prepared {len(tasks)} execution tasks across {len(batches)} dependency batches."
                    if tasks
                    else "No retrieval or tool tasks required."
                ),
                data={
                    "tasks": [asdict(task) for task in tasks],
                    "batches": [{"batch_id": batch.batch_id, "task_ids": batch.task_ids} for batch in batches],
                },
            )
        )

        execution = self._dispatch_task_graph(batches)
        trace.extend(execution["trace"])

        doc_results: list[RetrievalResult] = execution["doc_results"]
        tool_results: list[ToolResult] = execution["tool_results"]
        recovery_summary = self._build_recovery_summary(execution["outputs"], tool_results)
        doc_context = self.retriever.build_context(doc_results)
        tool_context = self._build_tool_context(tool_results)
        recovery_context = self._build_recovery_context(recovery_summary)

        if not doc_context and not tool_context:
            doc_context = "未检索到明显相关的本地投研资料。"

        answer_mode = "llm"
        try:
            answer = self._synthesize_answer(
                query,
                doc_context,
                tool_context,
                recovery_context=recovery_context,
                memory_messages=memory_messages,
            )
            answer = self._append_recovery_note(answer, recovery_summary)
        except Exception as exc:
            logger.warning("LLM response failed, fallback to evidence dump: %s", exc)
            answer_mode = "fallback"
            answer = self._build_fallback_answer(
                query,
                doc_context,
                tool_context,
                recovery_context,
                exc,
            )

        trace.append(
            AgentTraceStep(
                name="synthesize_answer",
                status="completed",
                detail=f"Answer generated via {answer_mode}.",
                data={"used_memory": bool(memory_messages), "memory_status": memory_status},
            )
        )

        if active_thread_id:
            self._persist_plan_memory(active_thread_id, query, plan)
            self._persist_execution_memory(
                active_thread_id,
                plan=plan,
                query=query,
                answer=answer,
                tool_results=tool_results,
                citations=[result.metadata for result in doc_results],
                trace=trace,
            )
            refreshed_summary = self.memory_service.maybe_refresh_summary(active_thread_id)
            refreshed_status = self.memory_service.get_memory_status(active_thread_id)
            trace.append(
                AgentTraceStep(
                    name="refresh_memory",
                    status="completed" if refreshed_summary else "skipped",
                    detail=(
                        "Conversation memory summary updated."
                        if refreshed_summary
                        else "Not enough history or changes to refresh memory summary."
                    ),
                    data=refreshed_status,
                )
            )

        citations = [result.metadata for result in doc_results]
        return AgentRunResult(
            answer=answer,
            citations=citations,
            tool_results=tool_results,
            plan=plan,
            trace=trace,
            recovery=recovery_summary,
        )

    def prepare_answer_context(
        self,
        query: str,
        thread_id: str | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> PreparedAnswerContext:
        active_thread_id = thread_id or ""
        base_plan = build_agent_plan(query)
        plan, planner_trace = self._select_plan(query, base_plan, thread_id=active_thread_id)
        if progress_callback is not None:
            progress_callback(
                "planning",
                {
                    "intent": plan.intent,
                    "planner_source": plan.planner_source,
                    "stage_count": len(plan.stages),
                },
            )
        trace: list[AgentTraceStep] = [
            AgentTraceStep(
                name="plan_query",
                status="completed",
                detail=summarize_plan(plan),
                data={
                    "plan": asdict(plan),
                    "stage_count": len(plan.stages),
                    "planner_source": plan.planner_source,
                },
            )
        ]
        trace.extend(planner_trace)

        if plan.stages:
            trace.append(
                AgentTraceStep(
                    name="build_plan_stages",
                    status="completed",
                    detail=f"Planner built {len(plan.stages)} explicit stage(s).",
                    data={"stages": [asdict(stage) for stage in plan.stages]},
                )
            )

        memory_messages: list[dict[str, str]] = []
        memory_status: dict[str, Any] = {}
        if active_thread_id:
            memory = self.memory_service.load_memory(active_thread_id)
            memory_messages = self.memory_service.build_context_messages(active_thread_id, query)
            memory_status = self.memory_service.get_memory_status(active_thread_id)
            if progress_callback is not None:
                progress_callback(
                    "memory_loaded",
                    {
                        "has_memory": memory.has_memory,
                        "message_count": len(memory_messages),
                    },
                )
            prior_message_count = max(0, len(memory_messages) - 1 - (1 if memory.summary else 0))
            trace.append(
                AgentTraceStep(
                    name="load_memory",
                    status="completed" if memory.has_memory else "skipped",
                    detail=(
                        f"Loaded {prior_message_count} prior context messages and "
                        f"{'an existing summary' if memory.summary else 'no summary'}."
                    ),
                    data=memory_status,
                )
            )

        self.retriever.index_documents()
        if progress_callback is not None:
            progress_callback("documents_indexed", {"vector_search_ready": True})

        direct_answer = self._handle_catalog_query(query, plan)
        if direct_answer is not None:
            if progress_callback is not None:
                progress_callback(
                    "direct_answer_ready",
                    {"direct_answer_mode": plan.direct_answer_mode},
                )
            trace.append(
                AgentTraceStep(
                    name="direct_answer",
                    status="completed",
                    detail=f"Direct mode: {plan.direct_answer_mode}",
                )
            )
            return PreparedAnswerContext(
                query=query,
                thread_id=thread_id,
                plan=plan,
                trace=trace,
                memory_messages=memory_messages,
                memory_status=memory_status,
                doc_context="",
                tool_context="",
                recovery_context="",
                citations=[],
                tool_results=[],
                recovery={},
                direct_answer=direct_answer,
            )

        tasks = build_execution_tasks(plan, query)
        batches = build_task_batches(tasks)
        if progress_callback is not None:
            progress_callback(
                "tasks_built",
                {
                    "task_count": len(tasks),
                    "batch_count": len(batches),
                },
            )
        trace.append(
            AgentTraceStep(
                name="decompose_tasks",
                status="completed" if tasks else "skipped",
                detail=(
                    f"Prepared {len(tasks)} execution tasks across {len(batches)} dependency batches."
                    if tasks
                    else "No retrieval or tool tasks required."
                ),
                data={
                    "tasks": [asdict(task) for task in tasks],
                    "batches": [{"batch_id": batch.batch_id, "task_ids": batch.task_ids} for batch in batches],
                },
            )
        )

        execution = self._dispatch_task_graph(batches, progress_callback=progress_callback)
        trace.extend(execution["trace"])

        doc_results: list[RetrievalResult] = execution["doc_results"]
        tool_results: list[ToolResult] = execution["tool_results"]
        recovery_summary = self._build_recovery_summary(execution["outputs"], tool_results)
        doc_context = self.retriever.build_context(doc_results)
        tool_context = self._build_tool_context(tool_results)
        recovery_context = self._build_recovery_context(recovery_summary)
        if progress_callback is not None:
            progress_callback(
                "evidence_ready",
                {
                    "citation_count": len(doc_results),
                    "tool_result_count": len(tool_results),
                    "has_recovery": recovery_summary.get("has_recovery", False),
                },
            )

        if not doc_context and not tool_context:
            doc_context = "未检索到明显相关的本地投研资料。"

        return PreparedAnswerContext(
            query=query,
            thread_id=thread_id,
            plan=plan,
            trace=trace,
            memory_messages=memory_messages,
            memory_status=memory_status,
            doc_context=doc_context,
            tool_context=tool_context,
            recovery_context=recovery_context,
            citations=[result.metadata for result in doc_results],
            tool_results=tool_results,
            recovery=recovery_summary,
            direct_answer=None,
        )

    def _build_answer_messages(
        self,
        query: str,
        doc_context: str,
        tool_context: str,
        *,
        recovery_context: str = "",
        memory_messages: list[dict[str, str]] | None = None,
    ) -> list[dict[str, str]]:
        prompt_parts = [
            f"用户问题：{query}",
            doc_context,
            tool_context,
            recovery_context,
            "请基于以上证据回答。若证据冲突，先说明冲突点，再给出判断。",
        ]
        messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        if memory_messages:
            messages.extend(memory_messages[:-1])
        messages.append({"role": "user", "content": "\n\n".join(part for part in prompt_parts if part)})
        return messages

    @staticmethod
    def _extract_stream_text_delta(chunk: Any) -> str:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            return ""
        delta = getattr(choices[0], "delta", None)
        if delta is None:
            return ""
        content = getattr(delta, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                else:
                    text = getattr(item, "text", None)
                    if text is not None:
                        parts.append(str(text))
            return "".join(parts)
        return str(content or "")

    def stream_answer(self, prepared: PreparedAnswerContext):
        if prepared.direct_answer is not None:
            yield prepared.direct_answer
            return

        messages = self._build_answer_messages(
            prepared.query,
            prepared.doc_context,
            prepared.tool_context,
            recovery_context=prepared.recovery_context,
            memory_messages=prepared.memory_messages,
        )
        last_exc: Exception | None = None
        for thinking_enabled in (False, True):
            try:
                chat = create_stock_chat(
                    temperature=0.3,
                    max_tokens=2048,
                    thinking_enabled=thinking_enabled,
                )
                for chunk in chat.stream(messages):
                    delta = self._extract_stream_text_delta(chunk)
                    if delta:
                        yield delta
                return
            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "Streaming synthesis failed with thinking_enabled=%s: %s",
                    thinking_enabled,
                    exc,
                )

        assert last_exc is not None
        raise last_exc

    def _select_plan(
        self,
        query: str,
        base_plan: AgentPlan,
        *,
        thread_id: str | None = None,
    ) -> tuple[AgentPlan, list[AgentTraceStep]]:
        reused_plan, reuse_trace = self._try_reuse_recent_plan(thread_id, query, base_plan)
        if reused_plan is not None:
            assert reuse_trace is not None
            return reused_plan, [reuse_trace]
        initial_trace = [reuse_trace] if reuse_trace is not None else []

        if not ENABLE_LLM_PLANNER or base_plan.direct_answer_mode is not None:
            initial_trace.append(
                AgentTraceStep(
                    name="llm_plan",
                    status="skipped",
                    detail="LLM planner disabled or direct-answer mode selected.",
                )
            )
            return base_plan, initial_trace

        try:
            stages_payload = self._generate_llm_stages(query, base_plan)
            plan = apply_planner_stages(base_plan, stages_payload, planner_source="llm")
            initial_trace.append(
                AgentTraceStep(
                    name="llm_plan",
                    status="completed",
                    detail=f"LLM planner produced {len(plan.stages)} stage(s).",
                )
            )
            return plan, initial_trace
        except Exception as exc:
            logger.warning("LLM planner fallback to rule plan: %s", exc)
            initial_trace.append(
                AgentTraceStep(
                    name="llm_plan",
                    status="failed",
                    detail=f"LLM planner unavailable, fallback to rule planner: {exc}",
                )
            )
            return base_plan, initial_trace

    def _try_reuse_recent_plan(
        self,
        thread_id: str | None,
        query: str,
        fallback_plan: AgentPlan,
    ) -> tuple[AgentPlan | None, AgentTraceStep | None]:
        if not thread_id:
            return None, None

        snapshot = self.memory_service.get_recent_plan_snapshot(thread_id)
        if not snapshot:
            return None, AgentTraceStep(
                name="plan_memory_reuse",
                status="skipped",
                detail="No recent plan snapshot found in conversation memory.",
            )

        snapshot_updated_at = snapshot.get("updated_at")
        is_fresh = self._is_recent_snapshot(snapshot_updated_at, PLAN_REUSE_MAX_AGE_HOURS)
        decision = evaluate_plan_reuse(
            query,
            fallback_plan.intent,
            snapshot,
            min_score=PLAN_REUSE_MIN_SCORE,
            is_fresh=is_fresh,
        )
        trace = AgentTraceStep(
            name="plan_memory_reuse",
            status="completed" if decision.should_reuse else "skipped",
            detail=(
                "Reused recent plan snapshot from conversation memory."
                if decision.should_reuse
                else "Recent plan snapshot did not pass reuse checks."
            ),
            data={"score": decision.score, "reasons": decision.reasons},
        )
        if not decision.should_reuse:
            return None, trace

        stages_payload = snapshot.get("stages")
        if not isinstance(stages_payload, list) or not stages_payload:
            trace.status = "failed"
            trace.detail = "Recent plan snapshot is missing stages."
            return None, trace

        try:
            plan = apply_planner_stages(fallback_plan, stages_payload, planner_source="memory_reuse")
            return plan, trace
        except Exception as exc:
            logger.info("Recent plan snapshot could not be reused: %s", exc)
            trace.status = "failed"
            trace.detail = f"Recent plan snapshot could not be normalized: {exc}"
            return None, trace

    @staticmethod
    def _is_recent_snapshot(updated_at: Any, max_age_hours: int) -> bool:
        if not updated_at:
            return False
        try:
            text = str(updated_at)
            if text.endswith("Z"):
                text = text[:-1] + "+00:00"
            parsed = datetime.fromisoformat(text)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            age_seconds = (datetime.now(timezone.utc) - parsed).total_seconds()
            return age_seconds <= max_age_hours * 3600
        except ValueError:
            return False

    def _persist_plan_memory(self, thread_id: str, query: str, plan: AgentPlan) -> None:
        topic_signals = extract_plan_topic_signals(query, plan.intent)
        self.memory_service.persist_plan_snapshot(
            thread_id,
            {
                "intent": plan.intent,
                "direct_answer_mode": plan.direct_answer_mode,
                "use_document_search": plan.use_document_search,
                "planner_source": plan.planner_source,
                "notes": plan.notes,
                "stages": [asdict(stage) for stage in plan.stages],
                "query": query,
                "keywords": topic_signals["keywords"],
                "stock_codes": topic_signals["stock_codes"],
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    def _persist_execution_memory(
        self,
        thread_id: str,
        *,
        plan: AgentPlan,
        query: str,
        answer: str,
        tool_results: list[ToolResult],
        citations: list[dict[str, Any]],
        trace: list[AgentTraceStep],
    ) -> None:
        self.memory_service.persist_execution_snapshot(
            thread_id,
            {
                "query": query,
                "intent": plan.intent,
                "planner_source": plan.planner_source,
                "summary": f"{query[:80]} -> {answer[:160]}",
                "answer_excerpt": answer[:300],
                "tool_names": [item.name for item in tool_results],
                "citation_filenames": [item.get("filename", "") for item in citations[:5]],
                "trace_steps": [item.name for item in trace[-8:]],
            },
        )

    def _generate_llm_stages(self, query: str, base_plan: AgentPlan) -> list[dict[str, Any]]:
        chat = create_stock_chat(temperature=0.1, max_tokens=1200, thinking_enabled=False)
        prompt = (
            f"{PLANNER_PROMPT}\n\n"
            f"用户问题:\n{query}\n\n"
            f"基础规则计划:\n{json.dumps(asdict(base_plan), ensure_ascii=False)}"
        )
        response = chat.invoke(
            [
                {"role": "system", "content": "你负责把用户问题拆成可执行阶段。"},
                {"role": "user", "content": prompt},
            ]
        )
        content = _extract_answer(response.content)
        return self._parse_llm_stage_payload(content)

    @staticmethod
    def _parse_llm_stage_payload(content: str) -> list[dict[str, Any]]:
        stripped = content.strip()
        try:
            parsed = json.loads(stripped)
            if not isinstance(parsed, list):
                raise ValueError("Planner output must be a JSON list.")
            return parsed
        except json.JSONDecodeError:
            start = stripped.find("[")
            end = stripped.rfind("]")
            if start == -1 or end == -1 or end <= start:
                raise ValueError("Planner output is not valid JSON.")
            parsed = json.loads(stripped[start : end + 1])
            if not isinstance(parsed, list):
                raise ValueError("Planner output must be a JSON list.")
            return parsed

    def _handle_catalog_query(self, query: str, plan: AgentPlan) -> str | None:
        if plan.direct_answer_mode == "count_documents":
            docs = self.retriever.list_documents()
            return f"当前本地共有 {len(docs)} 份投研报告。"

        if plan.direct_answer_mode == "latest_documents":
            latest_docs = self.retriever.find_latest_documents()
            if not latest_docs:
                return "未找到带日期的本地投研资料。"
            lines = [f"最近一批投研资料（共 {len(latest_docs)} 篇）："]
            for item in latest_docs:
                lines.append(f"- {item['filename']} ({item.get('published_at') or '未知日期'})")
            return "\n".join(lines)

        if plan.direct_answer_mode == "list_documents":
            keywords = extract_query_keywords(query, limit=4)
            docs: list[dict[str, Any]] = []
            matched_keyword = ""
            for candidate in keywords:
                docs = self.retriever.list_documents(keyword=candidate)
                if docs:
                    matched_keyword = candidate
                    break
            if not docs:
                docs = self.retriever.list_documents()
            if not docs:
                target = matched_keyword or query
                return f"未找到与“{target}”相关的本地投研资料。"
            lines = [f"本地投研资料清单（共 {len(docs)} 篇）："]
            for item in docs[:30]:
                lines.append(f"- {item['filename']} ({item.get('published_at') or '未知日期'})")
            if len(docs) > 30:
                lines.append(f"- 其余 {len(docs) - 30} 篇未展开")
            return "\n".join(lines)

        if plan.direct_answer_mode == "open_document":
            filename_match = FILENAME_PATTERN.search(query)
            if not filename_match:
                return None
            filename = filename_match.group(1)
            document = self.retriever.get_document(filename)
            if document:
                metadata = document["metadata"]
                content = document["content"][:1200]
                return f"文档：{metadata['filename']} ({metadata.get('published_at') or '未知日期'})\n\n{content}"

        return None

    def _dispatch_task_graph(
        self,
        batches: list[TaskBatch],
        *,
        progress_callback: ProgressCallback | None = None,
    ) -> dict[str, Any]:
        if not batches:
            return {"doc_results": [], "tool_results": [], "trace": [], "outputs": []}

        trace: list[AgentTraceStep] = []
        completed_outputs: dict[str, SubAgentOutput] = {}
        doc_results: list[RetrievalResult] = []
        tool_results: list[ToolResult] = []

        for batch in batches:
            if progress_callback is not None:
                progress_callback(
                    "batch_started",
                    {
                        "batch_id": batch.batch_id,
                        "task_ids": batch.task_ids,
                    },
                )
            batch_result = self._execute_task_batch(batch, completed_outputs)
            trace.extend(batch_result["trace"])
            for output in batch_result["outputs"]:
                completed_outputs[output.task.task_id] = output
                if output.doc_results:
                    doc_results = output.doc_results
                if output.tool_result is not None:
                    tool_results.append(output.tool_result)
            if progress_callback is not None:
                progress_callback(
                    "batch_finished",
                    {
                        "batch_id": batch.batch_id,
                        "task_ids": batch.task_ids,
                        "output_count": len(batch_result["outputs"]),
                    },
                )

        return {
            "doc_results": doc_results,
            "tool_results": tool_results,
            "trace": trace,
            "outputs": list(completed_outputs.values()),
        }

    @staticmethod
    def _dependency_failures(task: AgentTask, completed_outputs: dict[str, SubAgentOutput]) -> list[str]:
        failures: list[str] = []
        for task_id in task.depends_on:
            output = completed_outputs.get(task_id)
            if output is not None and not output.success:
                failures.append(task_id)
        return failures

    @staticmethod
    def _build_skipped_output(
        task: AgentTask,
        dependency_failures: list[str],
        decision: RecoveryDecision,
    ) -> SubAgentOutput:
        return SubAgentOutput(
            task=task,
            worker=task.worker,
            trace=[
                AgentTraceStep(
                    name="skip_downstream_task",
                    status="skipped",
                    detail=f"Skipped {task.task_id} after dependency failure.",
                    data={
                        "task_id": task.task_id,
                        "worker": task.worker,
                        "dependency_failures": dependency_failures,
                        "recovery_action": decision.action,
                        "reason": decision.reason,
                    },
                )
            ],
            summary_note=f"{task.name} skipped due to failed dependencies.",
            success=False,
            error_message="Dependency failure prevented task execution.",
            recovery_hint=decision.reason,
            degraded=True,
        )

    def _execute_task_batch(
        self,
        batch: TaskBatch,
        completed_outputs: dict[str, SubAgentOutput],
    ) -> dict[str, Any]:
        trace: list[AgentTraceStep] = [
            AgentTraceStep(
                name="dispatch_batch",
                status="completed",
                detail=f"Dispatching batch {batch.batch_id} with {len(batch.tasks)} task(s).",
                data={"batch_id": batch.batch_id, "task_ids": batch.task_ids},
            )
        ]

        if len(batch.tasks) == 1:
            output = self._run_subagent_task(batch.tasks[0], completed_outputs)
            trace.extend(output.trace)
            return {"outputs": [output], "trace": trace}

        ordered_outputs: list[SubAgentOutput] = []
        with ThreadPoolExecutor(max_workers=min(4, len(batch.tasks))) as executor:
            future_to_task = {
                executor.submit(self._run_subagent_task, task, completed_outputs): task
                for task in batch.tasks
            }
            for future in as_completed(future_to_task):
                ordered_outputs.append(future.result())

        ordered_outputs.sort(key=lambda item: item.task.order)
        for output in ordered_outputs:
            trace.extend(output.trace)
        return {"outputs": ordered_outputs, "trace": trace}

    def _run_subagent_task(
        self,
        task: AgentTask,
        completed_outputs: dict[str, SubAgentOutput],
    ) -> SubAgentOutput:
        dependency_failures = self._dependency_failures(task, completed_outputs)
        dependency_notes = [
            completed_outputs[task_id].summary_note
            for task_id in task.depends_on
            if task_id in completed_outputs and completed_outputs[task_id].summary_note
        ]
        worker = self.subagent_registry.get(task.worker)
        payload = SubAgentInput(task=task, dependency_notes=dependency_notes)
        try:
            output = worker.run(payload)
        except Exception as exc:
            output = SubAgentOutput(
                task=task,
                worker=task.worker,
                trace=[
                    AgentTraceStep(
                        name="subagent_runtime_failure",
                        status="failed",
                        detail=f"Unhandled worker exception in {task.worker}.",
                        data={
                            "task_id": task.task_id,
                            "worker": task.worker,
                            "error_message": str(exc),
                            "dependency_failures": dependency_failures,
                        },
                    )
                ],
                summary_note=f"{task.name} failed.",
                success=False,
                error_message=str(exc),
                recovery_hint="Retry the worker or continue with partial evidence.",
                degraded=True,
            )

        if output.success:
            return output

        decision = choose_recovery_policy(task, dependency_failures, task_success=output.success)
        output.trace.append(
            AgentTraceStep(
                name="recover_stage_failure",
                status="completed" if decision.action != "none" else "skipped",
                detail=f"Recovery decision for {task.task_id}: {decision.action}.",
                data={
                    "task_id": task.task_id,
                    "worker": task.worker,
                    "dependency_failures": dependency_failures,
                    "reason": decision.reason,
                },
            )
        )

        if decision.retry_without_dependencies and dependency_notes:
            retry_payload = SubAgentInput(task=task, dependency_notes=[])
            try:
                retried_output = worker.run(retry_payload)
            except Exception as exc:
                retried_output = SubAgentOutput(
                    task=task,
                    worker=task.worker,
                    trace=[],
                    summary_note=f"{task.name} retry failed.",
                    success=False,
                    error_message=str(exc),
                    recovery_hint="Retry without dependencies also failed.",
                    degraded=True,
                )
            if retried_output.tool_result is not None:
                retried_output.tool_result.recovered = retried_output.success
                retried_output.tool_result.degraded = True
                retried_output.tool_result.recovery_action = decision.action
                if not retried_output.tool_result.error_message and retried_output.error_message:
                    retried_output.tool_result.error_message = retried_output.error_message
            retried_output.trace.insert(
                0,
                AgentTraceStep(
                    name="retry_task_without_dependencies",
                    status="completed" if retried_output.success else "failed",
                    detail=f"Retried {task.task_id} without dependency notes.",
                    data={
                        "task_id": task.task_id,
                        "worker": task.worker,
                        "original_dependency_notes": dependency_notes,
                    },
                ),
            )
            retried_output.degraded = True
            return retried_output

        if decision.skip_dependents:
            return self._build_skipped_output(task, dependency_failures, decision)

        if output.tool_result is not None:
            output.tool_result.degraded = output.degraded or output.tool_result.degraded
            output.tool_result.recovery_action = decision.action
            if not output.tool_result.error_message and output.error_message:
                output.tool_result.error_message = output.error_message
        return output

    def _synthesize_answer(
        self,
        query: str,
        doc_context: str,
        tool_context: str,
        *,
        recovery_context: str = "",
        memory_messages: list[dict[str, str]] | None = None,
    ) -> str:
        chat = create_stock_chat(temperature=0.3, max_tokens=2048, thinking_enabled=False)
        prompt_parts = [
            f"用户问题：{query}",
            doc_context,
            tool_context,
            recovery_context,
            "请基于以上证据回答。若证据冲突，先说明冲突点，再给出判断。",
        ]
        messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
        if memory_messages:
            messages.extend(memory_messages[:-1])
        messages.append({"role": "user", "content": "\n\n".join(part for part in prompt_parts if part)})
        response = chat.invoke(messages)
        return _extract_answer(response.content)

    @staticmethod
    def _build_recovery_summary(
        outputs: list[SubAgentOutput],
        tool_results: list[ToolResult],
    ) -> dict[str, Any]:
        if not outputs:
            return {}

        stages: list[dict[str, Any]] = []
        recovered_count = 0
        degraded_count = 0
        failed_count = 0
        tool_map = {(item.worker, item.name): item for item in tool_results}

        for output in outputs:
            tool_result = tool_map.get((output.worker, output.task.name))
            recovered = bool(tool_result.recovered) if tool_result is not None else False
            degraded = output.degraded or (bool(tool_result.degraded) if tool_result is not None else False)
            status = _status_label(output.success, degraded, recovered)

            if status == "recovered":
                recovered_count += 1
            elif status == "degraded":
                degraded_count += 1
            elif status == "failed":
                failed_count += 1

            stages.append(
                {
                    "task_id": output.task.task_id,
                    "stage_id": output.task.stage_id,
                    "name": output.task.name,
                    "worker": output.worker,
                    "status": status,
                    "success": output.success,
                    "degraded": degraded,
                    "recovered": recovered,
                    "recovery_action": tool_result.recovery_action if tool_result is not None else "",
                    "error_message": output.error_message,
                    "recovery_hint": output.recovery_hint,
                    "summary_note": output.summary_note,
                }
            )

        recommendations = StockAgent._build_recovery_recommendations(stages)
        return {
            "has_recovery": recovered_count > 0 or degraded_count > 0 or failed_count > 0,
            "recovered_count": recovered_count,
            "degraded_count": degraded_count,
            "failed_count": failed_count,
            "severity": "error" if failed_count > 0 else "warning",
            "recommended_actions": recommendations,
            "stages": stages,
        }

    @staticmethod
    def _build_recovery_recommendations(stages: list[dict[str, Any]]) -> list[str]:
        recommendations: list[str] = []
        for item in stages:
            status = str(item.get("status") or "")
            worker = str(item.get("worker") or "")
            recovery_action = str(item.get("recovery_action") or "")

            if worker == "document_researcher" and status in {"failed", "degraded"}:
                recommendations.append(
                    "本地资料检索异常，当前更适合先参考实时工具结果；如需文档证据，建议稍后重试或重建索引。"
                )
            if worker == "market_analyst" and status in {"failed", "degraded"}:
                recommendations.append(
                    "行情或财务工具异常，当前更适合先参考本地研报结论；如需最新数值，建议稍后重试。"
                )
            if worker == "news_analyst" and status in {"failed", "degraded"}:
                recommendations.append(
                    "资讯检索不稳定，建议改成更具体的公司名、主题词或时间范围后再试。"
                )
            if worker == "stock_screener" and status in {"failed", "degraded"}:
                recommendations.append(
                    "选股阶段结果不完整，建议先缩小筛选条件，或拆成单一条件逐步筛选。"
                )
            if recovery_action == "retry_without_dependencies":
                recommendations.append(
                    "系统已尝试脱离上游依赖做降级执行；如果你更重视完整链路，可以换个问法后重新发起一次。"
                )

        unique_recommendations: list[str] = []
        for item in recommendations:
            if item not in unique_recommendations:
                unique_recommendations.append(item)
        return unique_recommendations

    @staticmethod
    def _build_recovery_context(recovery: dict[str, Any]) -> str:
        if not recovery or not recovery.get("has_recovery"):
            return ""
        lines = ["Execution recovery status:"]
        for item in recovery.get("stages", []):
            status = item.get("status", "unknown")
            name = item.get("name", "stage")
            worker = item.get("worker", "")
            detail = item.get("recovery_hint") or item.get("error_message") or item.get("summary_note")
            suffix = f" | worker={worker}" if worker else ""
            lines.append(f"- [{status}] {name}{suffix}: {detail}")
        recommendations = recovery.get("recommended_actions") or []
        if recommendations:
            lines.append("Recommended actions:")
            for item in recommendations[:3]:
                lines.append(f"- {item}")
        lines.append("If recovery happened, mention it briefly and separate confirmed evidence from missing parts.")
        return "\n".join(lines)

    @staticmethod
    def _append_recovery_note(answer: str, recovery: dict[str, Any]) -> str:
        if not recovery or not recovery.get("has_recovery"):
            return answer

        notes: list[str] = []
        if recovery.get("recovered_count", 0):
            notes.append(f"{recovery['recovered_count']} 个阶段已降级恢复")
        if recovery.get("degraded_count", 0):
            notes.append(f"{recovery['degraded_count']} 个阶段结果不完整")
        if recovery.get("failed_count", 0):
            notes.append(f"{recovery['failed_count']} 个阶段仍失败")
        if not notes:
            return answer

        summary = f"{answer}\n\n执行说明：本次调度中" + "，".join(notes) + "。"
        recommendations = recovery.get("recommended_actions") or []
        if recommendations:
            summary += "\n建议动作：" + "；".join(recommendations[:2]) + "。"
        return summary

    @staticmethod
    def _build_tool_context(tool_results: list[ToolResult]) -> str:
        if not tool_results:
            return ""
        lines = ["实时工具结果："]
        for item in tool_results:
            worker_suffix = f" | worker={item.worker}" if item.worker else ""
            lines.append(f"[{item.name}] 请求: {item.request}{worker_suffix}")
            if item.reason:
                lines.append(f"触发原因: {item.reason}")
            lines.append(item.content)
        return "\n".join(lines)

    @staticmethod
    def _build_fallback_answer(
        query: str,
        doc_context: str,
        tool_context: str,
        recovery_context: str,
        error: Exception,
    ) -> str:
        lines = [
            f"已检索到与“{query}”相关的材料，但当前无法调用大模型生成最终总结。",
            f"原因：{error}",
        ]
        if doc_context:
            lines.extend(["", doc_context])
        if tool_context:
            lines.extend(["", tool_context])
        if recovery_context:
            lines.extend(["", recovery_context])
        return "\n".join(lines)


_stock_agent: StockAgent | None = None


def create_stock_agent() -> StockAgent:
    return StockAgent()


def get_stock_agent() -> StockAgent:
    global _stock_agent
    if _stock_agent is None:
        _stock_agent = create_stock_agent()
    return _stock_agent


def run_stock_query_sync(query: str, thread_id: str | None = None) -> AgentRunResult:
    return get_stock_agent().run(query, thread_id=thread_id)


async def run_stock_query(query: str) -> str:
    result = await asyncio.to_thread(run_stock_query_sync, query)
    return result.answer
