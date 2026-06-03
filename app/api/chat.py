"""Chat API endpoints."""

from __future__ import annotations

import asyncio
import json
import logging
import queue
import threading
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from time import perf_counter
from typing import Any

from agents.stock_agent.agent import get_stock_agent, run_stock_query_sync
from agents.stock_agent.runtime import AgentTraceStep
from agents.stock_agent.runtime import AgentPlan, AgentTraceStep
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from services.db import get_chat_db

router = APIRouter(prefix="/api/chat", tags=["chat"])
logger = logging.getLogger(__name__)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_event(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _serialize_plan(plan: AgentPlan) -> dict[str, Any]:
    return {
        "intent": plan.intent,
        "direct_answer_mode": plan.direct_answer_mode,
        "use_document_search": plan.use_document_search,
        "planned_tools": [asdict(tool) for tool in plan.planned_tools],
        "notes": plan.notes,
        "stages": [asdict(stage) for stage in plan.stages],
        "planner_source": plan.planner_source,
    }


def _serialize_trace(steps: list[AgentTraceStep]) -> list[dict[str, Any]]:
    return [
        {"name": step.name, "status": step.status, "detail": step.detail, "data": step.data}
        for step in steps
    ]


def _serialize_result_metadata(result: Any) -> dict[str, Any]:
    return {
        "citations": result.citations,
        "tool_results": [asdict(tool_result) for tool_result in result.tool_results],
        "plan": _serialize_plan(result.plan),
        "trace": _serialize_trace(result.trace),
        "recovery": result.recovery,
    }


def _serialize_prepared_metadata(prepared: Any) -> dict[str, Any]:
    return {
        "citations": prepared.citations,
        "tool_results": [asdict(tool_result) for tool_result in prepared.tool_results],
        "plan": _serialize_plan(prepared.plan),
        "trace": _serialize_trace(prepared.trace),
        "recovery": prepared.recovery,
    }


class ChatRequest(BaseModel):
    query: str
    thread_id: str | None = None


class ChatResponse(BaseModel):
    thread_id: str
    title: str
    answer: str
    citations: list[dict[str, Any]]
    tool_results: list[dict[str, Any]]
    plan: dict[str, Any]
    trace: list[dict[str, Any]]
    recovery: dict[str, Any]
    created_at: str


class ThreadDetailResponse(BaseModel):
    thread_id: str
    title: str | None
    messages: list[dict[str, Any]]


class ChatHistoryItem(BaseModel):
    thread_id: str
    title: str | None
    created_at: str
    updated_at: str


class ChatHistoryResponse(BaseModel):
    chats: list[ChatHistoryItem]


class CreateChatRequest(BaseModel):
    title: str | None = None


class CreateChatResponse(BaseModel):
    thread_id: str
    id: int


def _ensure_chat_exists(thread_id: str) -> None:
    chat_db = get_chat_db()
    if not chat_db.get_chat(thread_id):
        chat_db.create_chat(thread_id, "新对话")


def _resolve_title(thread_id: str, request: ChatRequest, query: str) -> str:
    chat_db = get_chat_db()
    agent = get_stock_agent()
    title_generator = getattr(agent, "generate_sidebar_title", None) or agent.generate_title
    default_title = "新对话"

    if not request.thread_id:
        title = title_generator(query)
        chat_db.update_chat_title(thread_id, title)
        return title

    chat_record = chat_db.get_chat(thread_id)
    current_title = str(chat_record.get("title") or "").strip() if chat_record else ""
    if (
        not current_title
        or current_title == default_title
        or "theuser" in current_title.lower().replace(" ", "")
        or "wantsme" in current_title.lower().replace(" ", "")
        or "15个字以内" in current_title
        or current_title.lower().replace(" ", "").startswith("ref")
    ):
        title = title_generator(query)
        chat_db.update_chat_title(thread_id, title)
        return title
    return current_title


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Process a stock research query and return the full answer with metadata."""
    chat_db = get_chat_db()
    thread_id = request.thread_id or str(uuid.uuid4())
    created_at = _utc_now()

    _ensure_chat_exists(thread_id)
    chat_db.add_message(thread_id=thread_id, role="user", content=request.query)

    result = run_stock_query_sync(request.query, thread_id=thread_id)
    result_metadata = _serialize_result_metadata(result)
    title = _resolve_title(thread_id, request, request.query)

    chat_db.add_message(
        thread_id=thread_id,
        role="assistant",
        content=result.answer,
        metadata=result_metadata,
    )

    return ChatResponse(
        thread_id=thread_id,
        title=title,
        answer=result.answer,
        citations=result.citations,
        tool_results=result_metadata["tool_results"],
        plan=result_metadata["plan"],
        trace=result_metadata["trace"],
        recovery=result.recovery,
        created_at=created_at,
    )


@router.get("/history", response_model=ChatHistoryResponse)
def get_history() -> ChatHistoryResponse:
    """Get all chat history threads."""
    chat_db = get_chat_db()
    chats = chat_db.get_all_chats(limit=50)
    return ChatHistoryResponse(
        chats=[
            ChatHistoryItem(
                thread_id=chat.get("thread_id", ""),
                title=chat.get("title"),
                created_at=chat.get("created_at", ""),
                updated_at=chat.get("updated_at", ""),
            )
            for chat in chats
        ]
    )


@router.get("/history/{thread_id}", response_model=ThreadDetailResponse)
def get_messages(thread_id: str) -> ThreadDetailResponse:
    """Get messages for a specific thread with thread metadata."""
    chat_db = get_chat_db()
    chat_record = chat_db.get_chat(thread_id)
    if not chat_record:
        raise HTTPException(status_code=404, detail="Thread not found")

    return ThreadDetailResponse(
        thread_id=thread_id,
        title=chat_record.get("title"),
        messages=chat_db.get_messages(thread_id, limit=100),
    )


@router.post("/history", response_model=CreateChatResponse)
def create_chat(request: CreateChatRequest) -> CreateChatResponse:
    """Create a new chat thread."""
    chat_db = get_chat_db()
    thread_id = str(uuid.uuid4())
    chat_id = chat_db.create_chat(thread_id, request.title or "新对话")
    return CreateChatResponse(thread_id=thread_id, id=chat_id)


@router.delete("/history/{thread_id}")
def delete_chat(thread_id: str) -> dict[str, str]:
    """Delete a chat thread."""
    chat_db = get_chat_db()
    chat_db.delete_chat(thread_id)
    return {"status": "deleted", "thread_id": thread_id}


@router.get("/stats")
def get_stats() -> dict[str, Any]:
    """Get database and vector store stats."""
    from services.document_retriever import get_document_retriever

    retriever = get_document_retriever()
    stats = retriever.get_stats()
    return {
        "document_count": stats.get("document_count", 0),
        "chunk_count": stats.get("chunk_count", 0),
        "vector_ready": stats.get("vector_ready", False),
    }


@router.post("/stream")
def chat_stream(request: ChatRequest) -> EventSourceResponse:
    """Return a server-sent event stream for a chat response."""
    chat_db = get_chat_db()
    thread_id = request.thread_id or str(uuid.uuid4())
    created_at = _utc_now()
    request_started_at = perf_counter()

    _ensure_chat_exists(thread_id)
    chat_db.add_message(thread_id=thread_id, role="user", content=request.query)

    async def event_generator():
        logger.info(
            "stream_chat_started thread_id=%s has_existing_thread=%s query_preview=%r",
            thread_id,
            bool(request.thread_id),
            request.query[:80],
        )
        yield {
            "event": "message_start",
            "data": _json_event({"thread_id": thread_id, "created_at": created_at}),
        }

        try:
            loop = asyncio.get_running_loop()
            agent = get_stock_agent()
            stream_queue: queue.Queue[Any] = queue.Queue()
            prepared_sentinel = object()

            def record_progress(event_name: str, payload: dict[str, Any]) -> None:
                stream_queue.put(
                    {
                        "event": "status",
                        "data": _json_event({"event": event_name, "payload": payload}),
                    }
                )

            def produce_prepared_context() -> None:
                try:
                    prepared = agent.prepare_answer_context(
                        request.query,
                        thread_id=thread_id,
                        progress_callback=record_progress,
                    )
                    stream_queue.put(prepared)
                except Exception as exc:
                    stream_queue.put(exc)
                finally:
                    stream_queue.put(prepared_sentinel)

            preparation_thread = threading.Thread(target=produce_prepared_context, daemon=True)
            preparation_thread.start()

            prepared = None
            preparation_started_at = perf_counter()
            while True:
                item = await loop.run_in_executor(None, stream_queue.get)
                if item is prepared_sentinel:
                    break
                if isinstance(item, Exception):
                    raise item
                if isinstance(item, dict) and "event" in item and "data" in item:
                    yield item
                    continue
                prepared = item

            if prepared is None:
                raise RuntimeError("Preparation finished without a prepared answer context.")
            preparation_elapsed_ms = round((perf_counter() - preparation_started_at) * 1000, 1)
            logger.info(
                "stream_chat_prepared thread_id=%s elapsed_ms=%s direct_answer=%s citations=%s tools=%s planner=%s",
                thread_id,
                preparation_elapsed_ms,
                prepared.direct_answer is not None,
                len(prepared.citations),
                len(prepared.tool_results),
                prepared.plan.planner_source,
            )
            title = _resolve_title(thread_id, request, request.query) if request.thread_id else None
            answer_chunks: list[str] = []
            result_metadata = _serialize_prepared_metadata(prepared)

            if prepared.direct_answer is not None:
                answer_chunks.append(prepared.direct_answer)
                logger.info(
                    "stream_chat_direct_answer thread_id=%s chars=%s elapsed_ms=%s",
                    thread_id,
                    len(prepared.direct_answer),
                    round((perf_counter() - request_started_at) * 1000, 1),
                )
                yield {
                    "event": "answer_delta",
                    "data": _json_event({"delta": prepared.direct_answer}),
                }
            else:
                sentinel = object()
                chunk_queue: queue.Queue[Any] = queue.Queue()
                first_delta_sent = False
                stream_started_at = perf_counter()

                def produce_stream() -> None:
                    try:
                        for delta in agent.stream_answer(prepared):
                            chunk_queue.put(delta)
                    except Exception as exc:
                        chunk_queue.put(exc)
                    finally:
                        chunk_queue.put(sentinel)

                producer = threading.Thread(target=produce_stream, daemon=True)
                producer.start()

                while True:
                    item = await loop.run_in_executor(None, chunk_queue.get)
                    if item is sentinel:
                        break
                    if isinstance(item, Exception):
                        raise item
                    delta = str(item)
                    answer_chunks.append(delta)
                    if not first_delta_sent:
                        first_delta_sent = True
                        logger.info(
                            "stream_chat_first_delta thread_id=%s elapsed_ms=%s",
                            thread_id,
                            round((perf_counter() - request_started_at) * 1000, 1),
                        )
                    yield {
                        "event": "answer_delta",
                        "data": _json_event({"delta": delta}),
                    }
                logger.info(
                    "stream_chat_stream_complete thread_id=%s elapsed_ms=%s chars=%s",
                    thread_id,
                    round((perf_counter() - stream_started_at) * 1000, 1),
                    sum(len(chunk) for chunk in answer_chunks),
                )

            final_answer = "".join(answer_chunks)
            final_answer = agent._append_recovery_note(final_answer, prepared.recovery)
            final_answer = agent._inline_citation_labels(final_answer, prepared.citations)
            final_answer = agent._normalize_inline_citation_format(final_answer)
            final_answer = agent._strip_heading_trailing_citations(final_answer)
            final_answer = agent._rewrite_inference_citation_style(final_answer)
            prepared.citations = agent._filter_citations_by_answer_usage(final_answer, prepared.citations)
            citation_note = agent._build_citation_note(prepared.citations)
            if citation_note:
                final_answer = f"{final_answer}\n\n{citation_note}"
                yield {
                    "event": "answer_delta",
                    "data": _json_event({"delta": f"\n\n{citation_note}"}),
                }

            if title is None:
                title = _resolve_title(thread_id, request, final_answer or request.query)

            prepared.trace.append(
                AgentTraceStep(
                    name="synthesize_answer",
                    status="completed",
                    detail="Answer generated via streaming synthesis.",
                    data={
                        "used_memory": bool(prepared.memory_messages),
                        "memory_status": prepared.memory_status,
                    },
                )
            )
            result_metadata = _serialize_prepared_metadata(prepared)

            chat_db.add_message(
                thread_id=thread_id,
                role="assistant",
                content=final_answer,
                metadata=result_metadata,
            )

            agent._persist_plan_memory(thread_id, request.query, prepared.plan)
            agent._persist_execution_memory(
                thread_id,
                plan=prepared.plan,
                query=request.query,
                answer=final_answer,
                tool_results=prepared.tool_results,
                citations=prepared.citations,
                trace=prepared.trace,
            )
            refreshed_summary = agent.memory_service.maybe_refresh_summary(thread_id)
            refreshed_status = agent.memory_service.get_memory_status(thread_id)
            prepared.trace.append(
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
            result_metadata = _serialize_prepared_metadata(prepared)

            for tool_result in result_metadata["tool_results"]:
                yield {
                    "event": "tool_result",
                    "data": _json_event(tool_result),
                }

            for citation in prepared.citations:
                yield {
                    "event": "citations",
                    "data": _json_event(citation),
                }

            yield {
                "event": "plan",
                "data": _json_event(result_metadata["plan"]),
            }

            for trace_step in result_metadata["trace"]:
                yield {
                    "event": "trace",
                    "data": _json_event(trace_step),
                }

            yield {
                "event": "recovery",
                "data": _json_event(prepared.recovery),
            }

            yield {
                "event": "answer_done",
                "data": _json_event(
                    {
                        "thread_id": thread_id,
                        "created_at": created_at,
                        "title": title,
                        "answer": final_answer,
                        **result_metadata,
                    }
                ),
            }
            yield {"event": "done", "data": _json_event({"ok": True})}
            logger.info(
                "stream_chat_completed thread_id=%s total_elapsed_ms=%s answer_chars=%s",
                thread_id,
                round((perf_counter() - request_started_at) * 1000, 1),
                len(final_answer),
            )
        except Exception as exc:
            from services.llm import _llm_error_details

            error_details = _llm_error_details(exc)
            logger.exception(
                "stream_chat_failed thread_id=%s elapsed_ms=%s",
                thread_id,
                round((perf_counter() - request_started_at) * 1000, 1),
            )
            yield {
                "event": "error",
                "data": _json_event(
                    {
                        "message": error_details["detail"],
                        "category": error_details["category"],
                        "error_type": error_details["error_type"],
                        "status_code": error_details["status_code"],
                    }
                ),
            }
            yield {"event": "done", "data": _json_event({"ok": False})}

    return EventSourceResponse(event_generator())
