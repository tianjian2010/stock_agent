"""Runtime primitives for the stock research agent system."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from app.config import LLM_PLANNER_MAX_STAGES
from agents.stock_agent.time_router import IntentType, classify_intent

DOCUMENT_TERMS = (
    "\u7814\u62a5",
    "\u7814\u7a76\u62a5",
    "\u7814\u7a76\u62a5\u544a",
    "\u8d44\u6599",
    "\u6587\u6863",
    "\u6295\u7814",
    "\u6587\u4ef6",
    "\u62a5\u544a",
)
ANALYSIS_TERMS = (
    "\u5206\u6790",
    "\u603b\u7ed3",
    "\u89e3\u8bfb",
    "\u600e\u4e48\u770b",
    "\u903b\u8f91",
    "\u539f\u56e0",
    "\u5f71\u54cd",
    "\u5224\u65ad",
)
LATEST_DOCUMENT_TERMS = (
    "\u6700\u8fd1",
    "\u6700\u65b0",
    "\u65b0",
    "\u8fd1\u671f",
)
LIST_DOCUMENT_TERMS = (
    "\u5217\u51fa",
    "\u6e05\u5355",
    "\u6709\u54ea\u4e9b",
    "\u6709\u54ea\u51e0\u7bc7",
)
COUNT_DOCUMENT_TERMS = (
    "\u591a\u5c11",
    "\u51e0\u4e2a",
    "\u51e0\u4efd",
    "\u6570\u91cf",
    "\u603b\u6570",
)
MARKET_KEYWORDS = {
    "price": (
        "行情",
        "股价",
        "价格",
        "现价",
        "涨跌",
        "报价",
        "突破",
        "新高",
        "新低",
        "最高价",
        "最低价",
        "走势",
        "趋势",
        "涨势",
        "跌势",
        "震荡",
        "回调",
        "反弹",
        "支撑位",
        "压力位",
        "均线",
        "技术面",
        "K线",
    ),
    "finance": (
        "财务",
        "利润",
        "营收",
        "估值",
        "市盈率",
        "市净率",
    ),
    "money_flow": (
        "资金流",
        "主力",
        "净流入",
        "净流出",
    ),
    "news": (
        "新闻",
        "资讯",
        "消息",
        "动态",
        "催化",
    ),
    "screener": (
        "选股",
        "筛选",
        "筛出来",
        "条件股",
    ),
}
DIRECT_ANSWER_BLOCK_TERMS = (
    *ANALYSIS_TERMS,
    "总结",
    "归纳",
    "梳理",
    "值得投",
    "股票",
    "个股",
    "标的",
    "行情",
    "股价",
    "价格",
    "现价",
    "涨幅",
    "涨跌",
    "历史最高",
    "新高",
)
KEYWORD_PATTERN = re.compile(r"[A-Za-z0-9]{2,}|[\u4e00-\u9fff]{2,}")
STOP_WORDS = {
    "关于",
    "哪些",
    "什么",
    "怎么",
    "如何",
    "请问",
    "告诉",
    "查询",
    "看看",
    "分析",
    "研究",
    "报告",
    "资料",
    "文档",
    "研报",
    "最近",
    "最新",
    "一下",
    "帮我",
    "结合",
    "继续",
}
FILENAME_PATTERN = re.compile(
    r"([\w\u4e00-\u9fff&-]+\.(?:txt|docx|pdf|xlsx|xls|csv|mp3|wav|m4a|aac|flac|ogg|mp4))"
)
QUERY_DATE_PATTERN = re.compile(
    r"(20\d{2}[/-]\d{1,2}[/-]\d{1,2}|\d{1,2}[/-]\d{1,2}|20\d{2}年\d{1,2}月\d{1,2}日?|\d{1,2}月\d{1,2}日?)"
)
RELATIVE_DATE_TERMS = ("今天", "今日", "当天", "昨天", "昨日", "明天", "明日")
DATE_LIST_INTENT_TERMS = ("每个", "逐个", "整理", "显示", "列出", "清单", "看看")
STOCK_CODE_PATTERN = re.compile(r"(?<!\d)\d{6}(?!\d)")
SYMBOL_LOOKUP_TERMS = (
    "是什么股票",
    "什么股票",
    "对应什么股票",
    "对应的股票",
    "股票名称",
    "股票名",
    "简称",
    "全称",
    "叫什么",
)
SYMBOL_REFERENCE_TERMS = ("上面", "这些", "前面", "刚才", "上述")
SYMBOL_LOOKUP_EXCLUDE_TERMS = DOCUMENT_TERMS + ANALYSIS_TERMS + (
    "走势",
    "趋势",
    "涨跌",
    "涨幅",
    "估值",
    "财务",
    "资金流",
    "研判",
)
ALLOWED_STAGE_TYPES = {"retrieval", "tool"}
ALLOWED_WORKERS = {
    "document_researcher",
    "market_analyst",
    "news_analyst",
    "stock_screener",
    "market_state_checker",
}


@dataclass(slots=True)
class PlannedTool:
    name: str
    query: str
    reason: str


@dataclass(slots=True)
class PlanStage:
    stage_id: str
    stage_type: str
    title: str
    goal: str
    worker: str
    query: str
    depends_on: list[str] = field(default_factory=list)
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class AgentPlan:
    intent: str
    direct_answer_mode: str | None
    use_document_search: bool
    planned_tools: list[PlannedTool] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    stages: list[PlanStage] = field(default_factory=list)
    planner_source: str = "rule"


@dataclass(slots=True)
class AgentTraceStep:
    name: str
    status: str
    detail: str
    data: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class ToolResult:
    name: str
    request: str
    content: str
    reason: str = ""
    success: bool = True
    worker: str = ""
    degraded: bool = False
    recovered: bool = False
    recovery_action: str = ""
    error_message: str = ""


@dataclass(slots=True)
class AgentRunResult:
    answer: str
    citations: list[dict[str, object]]
    tool_results: list[ToolResult]
    plan: AgentPlan
    trace: list[AgentTraceStep]
    recovery: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class AgentTask:
    task_id: str
    task_type: str
    name: str
    query: str
    reason: str
    worker: str
    order: int
    depends_on: list[str] = field(default_factory=list)
    stage_id: str = ""
    metadata: dict[str, object] = field(default_factory=dict)


@dataclass(slots=True)
class TaskBatch:
    batch_id: int
    task_ids: list[str]
    tasks: list[AgentTask]


@dataclass(slots=True)
class ReuseDecision:
    should_reuse: bool
    score: float
    reasons: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RecoveryDecision:
    action: str
    reason: str
    retry_without_dependencies: bool = False
    continue_without_output: bool = False
    skip_dependents: bool = False


def build_agent_plan(query: str) -> AgentPlan:
    normalized_query = query.strip()
    direct_answer_mode = _detect_direct_answer_mode(normalized_query)
    planned_tools = _plan_tools(normalized_query)
    use_document_search = _should_use_document_search(
        normalized_query,
        direct_answer_mode=direct_answer_mode,
        planned_tools=planned_tools,
    )
    notes = _build_plan_notes(direct_answer_mode, planned_tools, use_document_search)
    intent = _classify_intent(direct_answer_mode, planned_tools, use_document_search)
    stages = _build_rule_plan_stages(
        normalized_query,
        direct_answer_mode=direct_answer_mode,
        planned_tools=planned_tools,
        use_document_search=use_document_search,
    )
    return AgentPlan(
        intent=intent,
        direct_answer_mode=direct_answer_mode,
        use_document_search=use_document_search,
        planned_tools=planned_tools,
        notes=notes,
        stages=stages,
        planner_source="rule",
    )


def summarize_plan(plan: AgentPlan) -> str:
    tool_names = [tool.name for tool in plan.planned_tools]
    direct_mode = plan.direct_answer_mode or "none"
    tools_display = ", ".join(tool_names) if tool_names else "none"
    return (
        f"intent={plan.intent}; direct={direct_mode}; "
        f"doc_search={plan.use_document_search}; tools={tools_display}; "
        f"stages={len(plan.stages)}; planner={plan.planner_source}"
    )


def build_execution_tasks(plan: AgentPlan, query: str) -> list[AgentTask]:
    if plan.stages:
        return _build_tasks_from_stages(plan.stages)
    return _build_fallback_tasks(plan, query)


def build_task_batches(tasks: list[AgentTask]) -> list[TaskBatch]:
    task_map = {task.task_id: task for task in tasks}
    pending = set(task_map)
    resolved: set[str] = set()
    batches: list[TaskBatch] = []
    batch_id = 0

    while pending:
        ready = sorted(
            (
                task_map[task_id]
                for task_id in pending
                if all(dep in resolved for dep in task_map[task_id].depends_on)
            ),
            key=lambda item: item.order,
        )
        if not ready:
            unresolved = ", ".join(sorted(pending))
            raise ValueError(f"Task dependency cycle detected among: {unresolved}")

        batches.append(
            TaskBatch(
                batch_id=batch_id,
                task_ids=[task.task_id for task in ready],
                tasks=ready,
            )
        )
        for task in ready:
            pending.remove(task.task_id)
            resolved.add(task.task_id)
        batch_id += 1

    return batches


def apply_planner_stages(
    base_plan: AgentPlan,
    stages_payload: list[dict[str, Any]],
    *,
    planner_source: str = "llm",
) -> AgentPlan:
    normalized_stages = normalize_stage_payloads(stages_payload, max_stages=LLM_PLANNER_MAX_STAGES)
    return AgentPlan(
        intent=base_plan.intent,
        direct_answer_mode=base_plan.direct_answer_mode,
        use_document_search=base_plan.use_document_search,
        planned_tools=base_plan.planned_tools,
        notes=base_plan.notes,
        stages=normalized_stages,
        planner_source=planner_source,
    )


def normalize_stage_payloads(
    stages_payload: list[dict[str, Any]],
    *,
    max_stages: int = LLM_PLANNER_MAX_STAGES,
) -> list[PlanStage]:
    if not isinstance(stages_payload, list):
        raise ValueError("Planner stages payload must be a list.")
    if not stages_payload:
        raise ValueError("Planner stages payload cannot be empty.")
    if len(stages_payload) > max_stages:
        raise ValueError(f"Planner stages exceed limit: {len(stages_payload)} > {max_stages}")

    normalized: list[PlanStage] = []
    seen_stage_ids: set[str] = set()

    for index, raw_stage in enumerate(stages_payload):
        if not isinstance(raw_stage, dict):
            raise ValueError("Each planner stage must be a dict.")

        stage_id = str(raw_stage.get("stage_id") or f"stage_{index + 1}").strip()
        stage_type = str(raw_stage.get("stage_type") or "").strip()
        title = str(raw_stage.get("title") or "").strip()
        goal = str(raw_stage.get("goal") or "").strip()
        worker = str(raw_stage.get("worker") or "").strip()
        query = str(raw_stage.get("query") or "").strip()
        depends_on_raw = raw_stage.get("depends_on") or []
        metadata = raw_stage.get("metadata") or {}

        if not stage_id or stage_id in seen_stage_ids:
            raise ValueError(f"Duplicate or empty stage_id: {stage_id!r}")
        if stage_type not in ALLOWED_STAGE_TYPES:
            raise ValueError(f"Unsupported stage_type: {stage_type!r}")
        if worker not in ALLOWED_WORKERS:
            raise ValueError(f"Unsupported worker: {worker!r}")
        if not title or not goal or not query:
            raise ValueError("Planner stage must include title, goal, and query.")
        if not isinstance(depends_on_raw, list):
            raise ValueError("depends_on must be a list.")
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be a dict.")

        depends_on = [str(item).strip() for item in depends_on_raw if str(item).strip()]
        normalized.append(
            PlanStage(
                stage_id=stage_id,
                stage_type=stage_type,
                title=title,
                goal=goal,
                worker=worker,
                query=query,
                depends_on=depends_on,
                metadata={str(key): value for key, value in metadata.items()},
            )
        )
        seen_stage_ids.add(stage_id)

    _validate_stage_dependencies(normalized)
    return normalized


def extract_plan_topic_signals(query: str, intent: str) -> dict[str, Any]:
    keywords = extract_query_keywords(query, limit=8)
    stock_codes = sorted(set(STOCK_CODE_PATTERN.findall(query)))
    return {
        "intent": intent,
        "keywords": keywords,
        "stock_codes": stock_codes,
        "query": query,
    }


def evaluate_plan_reuse(
    current_query: str,
    current_intent: str,
    snapshot: dict[str, Any],
    *,
    min_score: float,
    is_fresh: bool,
) -> ReuseDecision:
    if not snapshot:
        return ReuseDecision(False, 0.0, ["no snapshot"])
    if not is_fresh:
        return ReuseDecision(False, 0.0, ["snapshot expired"])

    current_signals = extract_plan_topic_signals(current_query, current_intent)
    snapshot_signals = {
        "intent": str(snapshot.get("intent") or ""),
        "keywords": [str(item) for item in snapshot.get("keywords") or []],
        "stock_codes": [str(item) for item in snapshot.get("stock_codes") or []],
    }

    score = 0.0
    reasons: list[str] = []

    if snapshot_signals["intent"] == current_signals["intent"]:
        score += 0.45
        reasons.append("intent match")
    else:
        reasons.append("intent mismatch")

    current_codes = set(current_signals["stock_codes"])
    snapshot_codes = set(snapshot_signals["stock_codes"])
    if current_codes and snapshot_codes and current_codes == snapshot_codes:
        score += 0.30
        reasons.append("stock codes match")
    elif current_codes or snapshot_codes:
        reasons.append("stock codes differ")
    else:
        reasons.append("no stock codes in either query")

    current_keywords = set(current_signals["keywords"])
    snapshot_keywords = set(snapshot_signals["keywords"])
    overlap = current_keywords & snapshot_keywords
    union = current_keywords | snapshot_keywords
    if overlap:
        score += 0.25
    keyword_ratio = (len(overlap) / len(union)) if union else 0.0
    score += min(keyword_ratio, 1.0) * 0.15
    if overlap:
        reasons.append(f"keyword overlap={len(overlap)}")
    else:
        reasons.append("no keyword overlap")

    return ReuseDecision(score >= min_score, round(score, 4), reasons)


def choose_recovery_policy(
    task: AgentTask,
    dependency_failures: list[str],
    *,
    task_success: bool,
) -> RecoveryDecision:
    if task_success:
        return RecoveryDecision(action="none", reason="task succeeded")

    if task.task_type == "retrieval":
        return RecoveryDecision(
            action="continue_without_output",
            reason="retrieval failure should not block independent market stages",
            continue_without_output=True,
        )

    if dependency_failures:
        return RecoveryDecision(
            action="retry_without_dependencies",
            reason="tool task can retry in degraded mode without failed upstream notes",
            retry_without_dependencies=True,
        )

    return RecoveryDecision(
        action="continue_without_output",
        reason="tool failure should preserve partial evidence from other tasks",
        continue_without_output=True,
    )


def extract_query_keywords(query: str, limit: int = 6) -> list[str]:
    keywords: list[str] = []
    normalized_query = query
    for stop_word in STOP_WORDS:
        normalized_query = normalized_query.replace(stop_word, " ")

    for token in KEYWORD_PATTERN.findall(normalized_query):
        token = token.strip()
        if len(token) < 2 or token in STOP_WORDS:
            continue
        if token not in keywords:
            keywords.append(token)
        if len(keywords) >= limit:
            break

    compact = re.sub(r"[^\u4e00-\u9fffA-Za-z0-9]", "", query)
    if len(keywords) <= 1 and len(compact) >= 2:
        for size in (4, 3, 2):
            for index in range(0, max(0, len(compact) - size + 1)):
                candidate = compact[index : index + size]
                if candidate in STOP_WORDS or candidate in keywords:
                    continue
                keywords.append(candidate)
                if len(keywords) >= limit:
                    return keywords[:limit]

    if not keywords and query.strip():
        keywords.append(query.strip()[:8])
    return keywords


def _validate_stage_dependencies(stages: list[PlanStage]) -> None:
    stage_ids = {stage.stage_id for stage in stages}
    for stage in stages:
        for dependency in stage.depends_on:
            if dependency not in stage_ids:
                raise ValueError(f"Unknown stage dependency: {dependency!r}")

    pending = {stage.stage_id for stage in stages}
    resolved: set[str] = set()
    stage_map = {stage.stage_id: stage for stage in stages}
    while pending:
        ready = [
            stage_id
            for stage_id in pending
            if all(dep in resolved for dep in stage_map[stage_id].depends_on)
        ]
        if not ready:
            raise ValueError("Planner stage dependency cycle detected.")
        for stage_id in ready:
            pending.remove(stage_id)
            resolved.add(stage_id)


def _build_rule_plan_stages(
    query: str,
    *,
    direct_answer_mode: str | None,
    planned_tools: list[PlannedTool],
    use_document_search: bool,
) -> list[PlanStage]:
    if direct_answer_mode is not None:
        return []

    stages: list[PlanStage] = []

    if use_document_search:
        stages.append(
            PlanStage(
                stage_id="stage_research_documents",
                stage_type="retrieval",
                title="检索本地投研资料",
                goal="先从本地研报和资料中提取研究背景、核心观点与证据。",
                worker="document_researcher",
                query=query,
            )
        )

    document_stage_ids = [stage.stage_id for stage in stages if stage.stage_type == "retrieval"]
    for planned_tool in planned_tools:
        tool_stage_id = f"stage_{planned_tool.name}"
        worker = _resolve_tool_worker(planned_tool.name)
        stages.append(
            PlanStage(
                stage_id=tool_stage_id,
                stage_type="tool",
                title=_build_tool_stage_title(planned_tool.name),
                goal=planned_tool.reason,
                worker=worker,
                query=planned_tool.query,
                depends_on=document_stage_ids.copy(),
                metadata={"tool_name": planned_tool.name},
            )
        )

    return stages


def _build_tasks_from_stages(stages: list[PlanStage]) -> list[AgentTask]:
    stage_id_to_task_id = {stage.stage_id: f"task_{stage.stage_id}" for stage in stages}
    tasks: list[AgentTask] = []

    for order, stage in enumerate(stages):
        task_name = "document_retrieval"
        if stage.stage_type == "tool":
            task_name = str(stage.metadata.get("tool_name", stage.stage_id))
        tasks.append(
            AgentTask(
                task_id=stage_id_to_task_id[stage.stage_id],
                task_type=stage.stage_type,
                name=task_name,
                query=stage.query,
                reason=stage.goal,
                worker=stage.worker,
                order=order,
                depends_on=[stage_id_to_task_id[dep] for dep in stage.depends_on],
                stage_id=stage.stage_id,
            )
        )

    return tasks


def _build_fallback_tasks(plan: AgentPlan, query: str) -> list[AgentTask]:
    tasks: list[AgentTask] = []
    next_order = 0
    retrieval_task_id: str | None = None

    if plan.use_document_search:
        retrieval_task_id = "retrieve_documents"
        tasks.append(
            AgentTask(
                task_id=retrieval_task_id,
                task_type="retrieval",
                name="document_retrieval",
                query=query,
                reason="Use local research documents as the main evidence base.",
                worker="document_researcher",
                order=next_order,
                stage_id="fallback_retrieval",
            )
        )
        next_order += 1

    tool_dependencies = [retrieval_task_id] if retrieval_task_id and plan.planned_tools else []
    for planned_tool in plan.planned_tools:
        worker = _resolve_tool_worker(planned_tool.name)
        tasks.append(
            AgentTask(
                task_id=f"tool_{planned_tool.name}_{next_order}",
                task_type="tool",
                name=planned_tool.name,
                query=planned_tool.query,
                reason=planned_tool.reason,
                worker=worker,
                order=next_order,
                depends_on=[task_id for task_id in tool_dependencies if task_id],
                stage_id=f"fallback_{planned_tool.name}",
            )
        )
        next_order += 1

    return tasks


def _build_tool_stage_title(tool_name: str) -> str:
    if tool_name == "mx_search":
        return "检索新闻与催化"
    if tool_name == "mx_select_stock":
        return "执行条件选股"
    if tool_name == "mx_data_money_flow":
        return "核查资金流向"
    if tool_name == "mx_data_finance":
        return "核查财务与估值"
    if tool_name == "mx_data_price":
        return "核查实时行情"
    if tool_name == "mx_market_state":
        return "研判行情趋势与突破"
    return f"执行工具 {tool_name}"


def _resolve_tool_worker(tool_name: str) -> str:
    if tool_name == "mx_search":
        return "news_analyst"
    if tool_name == "mx_select_stock":
        return "stock_screener"
    if tool_name == "mx_market_state":
        return "market_state_checker"
    return "market_analyst"


def _detect_direct_answer_mode(query: str) -> str | None:
    # 0. Check time-router intents first (window_stats, daily_digest)
    intent_result = classify_intent(query)
    if intent_result.intent == IntentType.WINDOW_STATS:
        return "window_stats"
    if intent_result.intent == IntentType.DAILY_DIGEST:
        return "daily_digest"

    has_document_term = any(term in query for term in DOCUMENT_TERMS)
    has_list_term = any(term in query for term in LIST_DOCUMENT_TERMS)
    has_relative_date = any(term in query for term in RELATIVE_DATE_TERMS)
    has_date = QUERY_DATE_PATTERN.search(query) is not None or has_relative_date
    has_date_list_intent = any(term in query for term in DATE_LIST_INTENT_TERMS)
    has_block_term = any(term in query for term in DIRECT_ANSWER_BLOCK_TERMS)

    if not has_block_term and has_date and has_document_term and (
        has_list_term
        or has_date_list_intent
        or any(term in query for term in ("哪", "哪些", "有", "看看"))
    ):
        return "documents_by_date"

    if (
        not has_block_term
        and any(term in query for term in LATEST_DOCUMENT_TERMS)
        and has_document_term
        and any(term in query for term in ("哪些", "哪几篇", "清单", "列出", "一批"))
    ):
        return "latest_documents"

    if (
        not has_block_term
        and any(term in query for term in COUNT_DOCUMENT_TERMS)
        and has_document_term
        and not any(term in query for term in ("哪些", "哪几篇", "有哪些", "列出", "清单"))
    ):
        return "count_documents"

    if not has_block_term and has_list_term and has_document_term:
        return "list_documents"

    if FILENAME_PATTERN.search(query):
        return "open_document"

    return None


def _plan_tools(query: str) -> list[PlannedTool]:
    planned_tools: list[PlannedTool] = []

    if _is_symbol_lookup_query(query):
        return [
            PlannedTool(
                name="mx_search",
                query=f"{query} 股票代码 对应 股票名称",
                reason="用户在查询股票代码对应的股票名称，优先走妙想快速映射。",
            )
        ]

    if any(word in query for word in MARKET_KEYWORDS["screener"]):
        return [
            PlannedTool(
                name="mx_select_stock",
                query=query,
                reason="用户明确提出选股或筛选条件。",
            )
        ]

    if any(word in query for word in MARKET_KEYWORDS["news"]):
        planned_tools.append(
            PlannedTool(
                name="mx_search",
                query=query,
                reason="查询包含新闻、资讯或催化信息。",
            )
        )

    # Market state check: trend/breakout keywords take priority
    _trend_terms = ("突破", "新高", "新低", "走势", "趋势", "涨势", "跌势", "震荡", "均线", "技术面")
    if any(word in query for word in _trend_terms):
        planned_tools.append(
            PlannedTool(
                name="mx_market_state",
                query=query,
                reason="用户询问突破、趋势或技术面，需要进行行情研判。",
            )
        )
    elif any(word in query for word in MARKET_KEYWORDS["money_flow"]):
        planned_tools.append(
            PlannedTool(
                name="mx_data_money_flow",
                query=f"{query} 主力资金流向",
                reason="核查资金流与主力动向。",
            )
        )
    elif any(word in query for word in MARKET_KEYWORDS["finance"]):
        planned_tools.append(
            PlannedTool(
                name="mx_data_finance",
                query=f"{query} 财务指标",
                reason="核查财务指标与估值信息。",
            )
        )
    elif any(word in query for word in MARKET_KEYWORDS["price"]) or STOCK_CODE_PATTERN.search(
        query
    ):
        planned_tools.append(
            PlannedTool(
                name="mx_data_price",
                query=f"{query} 最新价",
                reason="核查实时行情或显式股票代码对应的价格信息。",
            )
        )

    return planned_tools


def _should_use_document_search(
    query: str,
    *,
    direct_answer_mode: str | None,
    planned_tools: list[PlannedTool],
) -> bool:
    if direct_answer_mode is not None:
        return False

    if _is_symbol_lookup_query(query):
        return False

    if any(term in query for term in DOCUMENT_TERMS + ANALYSIS_TERMS):
        return True

    if not planned_tools:
        return True

    if planned_tools and any(term in query for term in ("结合", "对比", "依据", "支撑")):
        return True

    return False


def _build_plan_notes(
    direct_answer_mode: str | None,
    planned_tools: list[PlannedTool],
    use_document_search: bool,
) -> list[str]:
    notes: list[str] = []

    if direct_answer_mode is not None:
        notes.append("命中目录型问题，优先走直接回答。")
    if use_document_search:
        notes.append("先检索本地投研资料，再决定如何组织答案。")
    if planned_tools:
        notes.append("补充使用实时工具，增强行情、资讯或选股事实。")
    if not use_document_search and not planned_tools:
        notes.append("不需要外部工具，走基础回答路径。")

    return notes


def _classify_intent(
    direct_answer_mode: str | None,
    planned_tools: list[PlannedTool],
    use_document_search: bool,
) -> str:
    if direct_answer_mode == "window_stats":
        return "document_catalog_window_stats"
    if direct_answer_mode == "daily_digest":
        return "document_catalog_daily_digest"
    if direct_answer_mode == "documents_by_date":
        return "document_catalog_by_date"
    if direct_answer_mode == "latest_documents":
        return "document_catalog_latest"
    if direct_answer_mode == "count_documents":
        return "document_catalog_count"
    if direct_answer_mode == "list_documents":
        return "document_catalog_list"
    if direct_answer_mode == "open_document":
        return "document_lookup"

    tool_names = {tool.name for tool in planned_tools}
    if _is_symbol_lookup_plan(planned_tools):
        return "market_symbol_lookup"
    if "mx_select_stock" in tool_names:
        return "stock_screening"
    if tool_names & {
        "mx_search",
        "mx_data_money_flow",
        "mx_data_finance",
        "mx_data_price",
        "mx_market_state",
    }:
        return "market_augmented_analysis" if use_document_search else "market_lookup"
    if use_document_search:
        return "research_analysis"
    return "general_answer"


def _is_symbol_lookup_plan(planned_tools: list[PlannedTool]) -> bool:
    return any(
        tool.name == "mx_search" and "股票代码 对应 股票名称" in tool.query
        for tool in planned_tools
    )


def _is_symbol_lookup_query(query: str) -> bool:
    has_code = STOCK_CODE_PATTERN.search(query) is not None
    has_lookup_term = any(term in query for term in SYMBOL_LOOKUP_TERMS)
    has_code_word = "代码" in query or "证券代码" in query
    has_reference = any(term in query for term in SYMBOL_REFERENCE_TERMS)
    has_exclude = any(term in query for term in SYMBOL_LOOKUP_EXCLUDE_TERMS)

    if has_exclude:
        return False

    if has_code and (has_lookup_term or has_code_word):
        return True

    if has_lookup_term and has_code_word:
        return True

    if has_reference and has_code_word and any(term in query for term in ("名称", "简称", "全称", "叫什么")):
        return True

    return False


