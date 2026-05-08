"""Chat API endpoints."""

from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Any

from agents.stock_agent.agent import get_stock_agent, run_stock_query_sync
from agents.stock_agent.runtime import AgentTraceStep
from agents.stock_agent.runtime import AgentPlan, AgentTraceStep
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from services.db import get_chat_db

router = APIRouter(prefix="/api/chat", tags=["chat"])


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
    default_title = "新对话"

    if not request.thread_id:
        title = agent.generate_title(query)
        chat_db.update_chat_title(thread_id, title)
        return title

    chat_record = chat_db.get_chat(thread_id)
    current_title = str(chat_record.get("title") or "").strip() if chat_record else ""
    if not current_title or current_title == default_title:
        title = agent.generate_title(query)
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

    _ensure_chat_exists(thread_id)
    chat_db.add_message(thread_id=thread_id, role="user", content=request.query)

    async def event_generator():
        yield {
            "event": "message_start",
            "data": _json_event({"thread_id": thread_id, "created_at": created_at}),
        }

        try:
            loop = asyncio.get_running_loop()
            agent = get_stock_agent()
            progress_events: list[dict[str, Any]] = []

            def record_progress(event_name: str, payload: dict[str, Any]) -> None:
                progress_events.append({"event": event_name, "payload": payload})

            prepared = await loop.run_in_executor(
                None,
                lambda: agent.prepare_answer_context(
                    request.query,
                    thread_id=thread_id,
                    progress_callback=record_progress,
                ),
            )
            title = _resolve_title(thread_id, request, request.query)
            answer_chunks: list[str] = []
            result_metadata = _serialize_prepared_metadata(prepared)

            for progress_event in progress_events:
                yield {
                    "event": "status",
                    "data": _json_event(progress_event),
                }

            if prepared.direct_answer is not None:
                answer_chunks.append(prepared.direct_answer)
                yield {
                    "event": "answer_delta",
                    "data": _json_event({"delta": prepared.direct_answer}),
                }
            else:
                stream_iter = await loop.run_in_executor(None, lambda: list(agent.stream_answer(prepared)))
                for delta in stream_iter:
                    answer_chunks.append(delta)
                    yield {
                        "event": "answer_delta",
                        "data": _json_event({"delta": delta}),
                    }

            final_answer = "".join(answer_chunks)
            final_answer = agent._append_recovery_note(final_answer, prepared.recovery)

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
        except Exception as exc:
            import logging as _logging
            _logging.getLogger(__name__).exception("Stream chat failed for thread %s", thread_id)
            yield {"event": "error", "data": _json_event({"message": str(exc)})}
            yield {"event": "done", "data": _json_event({"ok": False})}

    return EventSourceResponse(event_generator())
