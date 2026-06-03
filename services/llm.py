"""MiniMax-compatible LLM service wrappers built on the OpenAI client."""

import logging
import re
from dataclasses import dataclass
from typing import Any

import requests
from openai import APIConnectionError, APIStatusError, APITimeoutError, AsyncOpenAI, OpenAI

from app.config import (
    EMBEDDING_API_KEY,
    EMBEDDING_BASE_URL,
    EMBEDDING_PROVIDER,
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    LLM_STARTUP_HEALTHCHECK_TIMEOUT_SECONDS,
    MINIMAX_API_KEY,
    MINIMAX_BASE_URL,
    MINIMAX_MODEL,
    OPENAI_API_KEY,
    THINKING_ENABLED,
)

logger = logging.getLogger(__name__)


def _require_api_key() -> str:
    if not MINIMAX_API_KEY:
        raise ValueError(
            "Missing MINIMAX_API_KEY. Please set it in the environment before using the LLM features."
        )
    return MINIMAX_API_KEY


def _normalize_minimax_base_url(base_url: str) -> str:
    normalized = (base_url or "").strip()
    if not normalized:
        return "https://api.minimaxi.com/v1"
    return normalized.rstrip("/")


@dataclass(slots=True)
class ChatResult:
    content: str


def _mask_api_key(api_key: str) -> str:
    value = (api_key or "").strip()
    if not value:
        return "missing"
    if len(value) <= 10:
        return "set"
    return f"{value[:4]}...{value[-2:]}"


def _extract_status_code(exc: Exception) -> Any:
    status_code = getattr(exc, "status_code", None)
    if status_code is not None:
        return status_code
    response = getattr(exc, "response", None)
    return getattr(response, "status_code", "unknown")


def _extract_error_text(exc: Exception) -> str:
    body = getattr(exc, "body", None)
    if body:
        return str(body)

    response = getattr(exc, "response", None)
    if response is not None:
        text = getattr(response, "text", None)
        if text:
            return str(text)
        try:
            json_body = response.json()
        except Exception:
            json_body = None
        if json_body:
            return str(json_body)
    return str(exc)


def _classify_llm_exception(exc: Exception) -> str:
    if isinstance(exc, APITimeoutError):
        return "timeout"
    if isinstance(exc, APIConnectionError):
        return "connection_error"
    if isinstance(exc, APIStatusError):
        if getattr(exc, "status_code", None) == 401:
            return "invalid_api_key"
        if getattr(exc, "status_code", None) == 404:
            return "bad_base_url"

    lower_message = str(exc).lower()
    if "invalid api key" in lower_message or "authorized_error" in lower_message or "401" in lower_message:
        return "invalid_api_key"
    if "connection error" in lower_message:
        return "connection_error"
    if "timeout" in lower_message:
        return "timeout"
    if "404" in lower_message or "not found" in lower_message:
        return "bad_base_url"
    return type(exc).__name__


def _llm_error_details(exc: Exception) -> dict[str, Any]:
    return {
        "category": _classify_llm_exception(exc),
        "error_type": type(exc).__name__,
        "status_code": _extract_status_code(exc),
        "detail": _extract_error_text(exc),
    }


def describe_minimax_chat_config() -> dict[str, Any]:
    normalized_base_url = _normalize_minimax_base_url(MINIMAX_BASE_URL)
    return {
        "provider": "minimax",
        "model": MINIMAX_MODEL,
        "base_url": normalized_base_url,
        "base_url_source": MINIMAX_BASE_URL or "",
        "api_key_present": bool(MINIMAX_API_KEY),
        "api_key_preview": _mask_api_key(MINIMAX_API_KEY),
    }


def diagnose_minimax_auth() -> dict[str, Any]:
    config = describe_minimax_chat_config()
    result: dict[str, Any] = {
        **config,
        "ok": False,
        "category": "unknown",
        "message": "",
    }

    if not MINIMAX_API_KEY:
        result["category"] = "missing_api_key"
        result["message"] = "MINIMAX_API_KEY is missing."
        return result

    try:
        client = OpenAI(api_key=MINIMAX_API_KEY, base_url=config["base_url"])
        client.chat.completions.create(
            model=MINIMAX_MODEL,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=8,
            temperature=0,
            extra_body={},
            timeout=LLM_STARTUP_HEALTHCHECK_TIMEOUT_SECONDS,
        )
        result["ok"] = True
        result["category"] = "ok"
        result["message"] = "MiniMax chat authentication check passed."
        return result
    except Exception as exc:
        details = _llm_error_details(exc)
        result["message"] = details["detail"]
        result["category"] = details["category"]
        result["error_type"] = details["error_type"]
        result["status_code"] = details["status_code"]
        return result


class OpenAICompatibleChatModel:
    """Simple chat model wrapper with a LangChain-like invoke interface."""

    def __init__(
        self,
        model: str,
        temperature: float,
        max_tokens: int | None,
        thinking_enabled: bool,
    ):
        if not (0 <= temperature <= 2):
            raise ValueError(f"temperature must be in [0, 2], got {temperature}")
        if max_tokens is not None and max_tokens <= 0:
            raise ValueError(f"max_tokens must be positive, got {max_tokens}")

        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.thinking_enabled = thinking_enabled
        self.base_url = _normalize_minimax_base_url(MINIMAX_BASE_URL)
        self.client = OpenAI(
            api_key=_require_api_key(),
            base_url=self.base_url,
        )
        self.async_client = AsyncOpenAI(
            api_key=_require_api_key(),
            base_url=self.base_url,
        )

    def invoke(self, messages: list[Any]) -> ChatResult:
        normalized_messages = self._normalize_messages(messages)
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=normalized_messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                extra_body=self._build_extra_body(),
            )
        except Exception as exc:
            details = _llm_error_details(exc)
            logger.error(
                "LLM invoke failed: category=%s, error_type=%s, status=%s, model=%s, base_url=%s, "
                "temperature=%s, max_tokens=%s, thinking_requested=%s, thinking_global=%s, "
                "message_count=%s, error=%s",
                details["category"],
                details["error_type"],
                details["status_code"],
                self.model,
                self.base_url,
                self.temperature,
                self.max_tokens,
                self.thinking_enabled,
                THINKING_ENABLED,
                len(normalized_messages),
                details["detail"],
            )
            raise
        if not response.choices:
            logger.warning(
                "LLM invoke returned empty choices: model=%s, temperature=%s, max_tokens=%s, thinking=%s",
                self.model, self.temperature, self.max_tokens, self.thinking_enabled,
            )
            return ChatResult(content="")
        return ChatResult(content=response.choices[0].message.content or "")

    async def ainvoke(self, messages: list[Any]) -> ChatResult:
        normalized_messages = self._normalize_messages(messages)
        try:
            response = await self.async_client.chat.completions.create(
                model=self.model,
                messages=normalized_messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                extra_body=self._build_extra_body(),
            )
        except Exception as exc:
            details = _llm_error_details(exc)
            logger.error(
                "LLM ainvoke failed: category=%s, error_type=%s, status=%s, model=%s, base_url=%s, "
                "temperature=%s, max_tokens=%s, thinking_requested=%s, thinking_global=%s, "
                "message_count=%s, error=%s",
                details["category"],
                details["error_type"],
                details["status_code"],
                self.model,
                self.base_url,
                self.temperature,
                self.max_tokens,
                self.thinking_enabled,
                THINKING_ENABLED,
                len(normalized_messages),
                details["detail"],
            )
            raise
        if not response.choices:
            logger.warning(
                "LLM ainvoke returned empty choices: model=%s, thinking=%s",
                self.model, self.thinking_enabled,
            )
            return ChatResult(content="")
        return ChatResult(content=response.choices[0].message.content or "")

    def stream(self, messages: list[Any]) -> Any:
        """Streaming chat completion yielding deltas."""
        normalized_messages = self._normalize_messages(messages)
        try:
            return self.client.chat.completions.create(
                model=self.model,
                messages=normalized_messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                extra_body=self._build_extra_body(),
                stream=True,
            )
        except Exception as exc:
            details = _llm_error_details(exc)
            logger.error(
                "LLM stream failed: category=%s, error_type=%s, status=%s, model=%s, base_url=%s, "
                "temperature=%s, max_tokens=%s, thinking_requested=%s, thinking_global=%s, "
                "message_count=%s, error=%s",
                details["category"],
                details["error_type"],
                details["status_code"],
                self.model,
                self.base_url,
                self.temperature,
                self.max_tokens,
                self.thinking_enabled,
                THINKING_ENABLED,
                len(normalized_messages),
                details["detail"],
            )
            raise

    async def astream(self, messages: list[Any]) -> Any:
        """Async streaming chat completion yielding deltas."""
        normalized_messages = self._normalize_messages(messages)
        try:
            async for chunk in await self.async_client.chat.completions.create(
                model=self.model,
                messages=normalized_messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                extra_body=self._build_extra_body(),
                stream=True,
            ):
                yield chunk
        except Exception as exc:
            details = _llm_error_details(exc)
            logger.error(
                "LLM astream failed: category=%s, error_type=%s, status=%s, model=%s, base_url=%s, "
                "temperature=%s, max_tokens=%s, thinking_requested=%s, thinking_global=%s, "
                "message_count=%s, error=%s",
                details["category"],
                details["error_type"],
                details["status_code"],
                self.model,
                self.base_url,
                self.temperature,
                self.max_tokens,
                self.thinking_enabled,
                THINKING_ENABLED,
                len(normalized_messages),
                details["detail"],
            )
            raise

    def _build_extra_body(self) -> dict[str, Any]:
        # Only include thinking param when globally enabled AND this instance requests it.
        # MiniMax-M2.7 does NOT support the thinking/reasoning param and returns
        # error 2013 ("invalid chat setting") if it is sent.
        if not THINKING_ENABLED or not self.thinking_enabled:
            return {}
        return {"thinking": {"type": "reasoning", "budget": 2048}}

    @staticmethod
    def _extract_text(content: Any) -> str:
        """Extract plain text from message content (handles str or list)."""
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                else:
                    parts.append(str(item))
            return "\n".join(parts)
        return str(content)

    @staticmethod
    def _normalize_messages(messages: list[Any]) -> Any:
        raw: list[dict[str, str]] = []
        for message in messages:
            if isinstance(message, dict):
                raw.append(
                    {
                        "role": str(message.get("role", "user")),
                        "content": OpenAICompatibleChatModel._extract_text(
                            message.get("content", "")
                        ),
                    }
                )
                continue

            role = "user"
            class_name = type(message).__name__.lower()
            if "system" in class_name:
                role = "system"
            elif "ai" in class_name or "assistant" in class_name:
                role = "assistant"

            content = getattr(message, "content", message)
            raw.append(
                {"role": role, "content": OpenAICompatibleChatModel._extract_text(content)}
            )

        # MiniMax-M2.7 rejects consecutive messages with the same role
        # (especially consecutive system messages) with error 2013.
        # Merge adjacent same-role messages into one.
        if not raw:
            return raw
        merged: list[dict[str, str]] = [raw[0]]
        for msg in raw[1:]:
            if msg["role"] == merged[-1]["role"]:
                merged[-1]["content"] += "\n\n" + msg["content"]
            else:
                merged.append(msg)
        return merged


class OpenAICompatibleEmbeddings:
    """Embedding wrapper with a LangChain-like interface."""

    def __init__(
        self,
        model: str,
        dimensions: int | None = None,
        *,
        provider: str,
        api_key: str,
        base_url: str | None = None,
    ):
        self.model = model
        self.dimensions = dimensions
        self.provider = provider
        self.api_key = api_key
        self.base_url = base_url.strip() if base_url else None
        client_kwargs: dict[str, Any] = {"api_key": api_key}
        if self.base_url:
            client_kwargs["base_url"] = self.base_url
        self.client = OpenAI(**client_kwargs)

    @property
    def configured(self) -> bool:
        if not self.model:
            return False
        if self.provider == "ollama":
            return bool(self.base_url)
        return bool(self.api_key)

    def describe(self) -> str:
        visible_key = "set" if self.api_key else "missing"
        return (
            f"provider={self.provider}, model={self.model}, "
            f"base_url={self.base_url or '<default>'}, dimensions={self.dimensions}, api_key={visible_key}"
        )

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        if not self.configured:
            raise RuntimeError(
                "Embedding provider is not fully configured: "
                f"{self.describe()}"
            )

        # Process in batches to avoid API payload limits
        batch_size = 128
        results: list[list[float]] = []

        for i in range(0, len(texts), batch_size):
            batch = texts[i : i + batch_size]
            batch_embeddings = self._embed_batch(batch, request_type="db")
            results.extend(batch_embeddings)

        return results

    def embed_query(self, query: str) -> list[float]:
        embeddings = self._embed_batch([query], request_type="query")
        return embeddings[0]

    def _embed_batch(self, batch: list[str], *, request_type: str) -> list[list[float]]:
        if self.provider == "minimax":
            return self._embed_batch_minimax(batch, request_type=request_type)

        use_dimensions = self.dimensions is not None
        try:
            return self._embed_batch_once(batch, use_dimensions=use_dimensions)
        except Exception as exc:
            if use_dimensions and self._should_retry_without_dimensions(exc):
                logger.warning(
                    "Embedding request failed with dimensions for %s; retrying without dimensions",
                    self.describe(),
                )
                return self._embed_batch_once(batch, use_dimensions=False)
            raise

    def _embed_batch_minimax(self, batch: list[str], *, request_type: str) -> list[list[float]]:
        url = f"{(self.base_url or '').rstrip('/')}/embeddings"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "texts": batch,
            "type": request_type,
        }

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=60)
            response.raise_for_status()
        except Exception as exc:
            raise RuntimeError(
                "MiniMax embedding request failed "
                f"({self.describe()}, status={_extract_status_code(exc)}, error={_extract_error_text(exc)})"
            ) from exc

        try:
            payload = response.json()
        except Exception as exc:
            raise RuntimeError(
                "MiniMax embedding response was not valid JSON "
                f"({self.describe()}, status={response.status_code}, body={response.text[:500]})"
            ) from exc

        base_resp = payload.get("base_resp") or {}
        status_code = base_resp.get("status_code", response.status_code)
        status_msg = base_resp.get("status_msg", "")
        vectors = payload.get("vectors")

        if status_code not in (0, "0", 200, "200") and not vectors:
            raise RuntimeError(
                "MiniMax embedding API returned an error "
                f"({self.describe()}, status={status_code}, error={status_msg or payload})"
            )
        if not vectors:
            raise RuntimeError(
                "No embedding data received "
                f"({self.describe()}, status={status_code}, error={status_msg or payload})"
            )
        return vectors

    def _embed_batch_once(self, batch: list[str], *, use_dimensions: bool) -> list[list[float]]:
        kwargs: dict[str, Any] = {"model": self.model, "input": batch}
        if use_dimensions and self.dimensions is not None:
            kwargs["dimensions"] = self.dimensions

        try:
            response = self.client.embeddings.create(**kwargs)
        except Exception as exc:
            raise RuntimeError(
                "Embedding request failed "
                f"({self.describe()}, status={_extract_status_code(exc)}, error={_extract_error_text(exc)})"
            ) from exc

        data = getattr(response, "data", None) or []
        if not data:
            raise RuntimeError(f"No embedding data received ({self.describe()})")

        embeddings: list[list[float]] = []
        for item in data:
            embedding = getattr(item, "embedding", None)
            if not embedding:
                raise RuntimeError(f"Embedding item missing vector payload ({self.describe()})")
            embeddings.append(embedding)
        return embeddings

    @staticmethod
    def _should_retry_without_dimensions(exc: Exception) -> bool:
        message = str(exc).lower()
        return any(
            token in message
            for token in ("dimension", "dimensions", "unknown parameter", "extra inputs")
        )


def create_embedding_model() -> OpenAICompatibleEmbeddings:
    """Create the embedding model for vector search."""
    provider = EMBEDDING_PROVIDER or "minimax"
    api_key = EMBEDDING_API_KEY
    base_url = EMBEDDING_BASE_URL or None

    if provider == "minimax":
        api_key = api_key or MINIMAX_API_KEY
        base_url = _normalize_minimax_base_url(base_url or MINIMAX_BASE_URL)
    elif provider == "openai":
        api_key = api_key or OPENAI_API_KEY
    elif provider == "ollama":
        base_url = base_url or "http://localhost:11434/v1"
        api_key = api_key or "ollama"

    return OpenAICompatibleEmbeddings(
        model=EMBEDDING_MODEL,
        dimensions=EMBEDDING_DIMENSION,
        provider=provider,
        api_key=api_key,
        base_url=base_url,
    )

def create_minimax_chat(
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int | None = None,
    thinking_enabled: bool = True,
) -> OpenAICompatibleChatModel:
    """Create a MiniMax-compatible chat model instance."""
    return OpenAICompatibleChatModel(
        model=model or MINIMAX_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        thinking_enabled=thinking_enabled,
    )


def create_stock_chat(
    temperature: float = 0.7,
    max_tokens: int = 4096,
    thinking_enabled: bool = True,
) -> OpenAICompatibleChatModel:
    """Create the main stock research chat model."""
    return create_minimax_chat(
        model=MINIMAX_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        thinking_enabled=thinking_enabled,
    )


# ----------------------------------------------------------------------
# Token counting utilities for context window budget control
# ----------------------------------------------------------------------
# MiniMax-M2.7 context window: 204,800 tokens (input side).
# Conservative default budget: 100 000 tokens for the input context
# (leaving ~100 000 for the model to generate a response).
_TOKENS_PER_MESSAGE_OVERHEAD = 4  # role + formatting tags per message


def estimate_tokens_for_text(text: str) -> int:
    """
    Rough token estimate for a piece of text.

    Based on the fact that:
      - Chinese characters average ~1.5 tokens each.
      - English words average ~1.3 tokens each.
      - Digits and punctuation add ~0.4 tokens per character.
    """
    if not text:
        return 0
    chinese_chars = sum(1 for ch in text if "一" <= ch <= "鿿")
    # Count English word-like tokens (alphabetic sequences).
    english_words = len(_ENGLISH_WORD_RE.findall(text))
    other_chars = len(text) - chinese_chars - sum(len(w) for w in _ENGLISH_WORD_RE.findall(text))
    return int(chinese_chars * 1.5) + int(english_words * 1.3) + int(other_chars * 0.4)


_ENGLISH_WORD_RE = re.compile(r"[A-Za-z]+")


def count_messages_tokens(messages: list[dict[str, str]]) -> int:
    """Return approximate total token count for a list of messages."""
    total = 0
    for msg in messages:
        total += _TOKENS_PER_MESSAGE_OVERHEAD
        total += estimate_tokens_for_text(msg.get("content", ""))
    return total


def truncate_text_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate a single text block to fit within max_tokens."""
    if max_tokens <= 0:
        return ""
    tokens = estimate_tokens_for_text(text)
    if tokens <= max_tokens:
        return text
    # Binary-search for the right length (max 8 iterations).
    low, high = 0, len(text)
    for _ in range(8):
        mid = (low + high) // 2
        if estimate_tokens_for_text(text[:mid]) <= max_tokens:
            low = mid
        else:
            high = mid
        if high - low <= 1:
            break
    return text[:low]


# Priority order for truncation (low → high, lowest gets cut first).
# memory_system = messages whose content starts with "当前会话长期记忆摘要" or
#                 "最近一次执行摘要"
_MEMORY_SUMMARY_LABELS = ("当前会话长期记忆摘要", "最近一次执行摘要")


def _is_low_priority_memory(msg: dict[str, str]) -> bool:
    content = msg.get("content", "")
    role = msg.get("role", "")
    if role != "system":
        return False
    return content.startswith(_MEMORY_SUMMARY_LABELS)


def truncate_messages_by_budget(
    messages: list[dict[str, str]],
    max_tokens: int,
    *,
    always_keep_roles: tuple[str, ...] = ("system", "user"),
    always_keep_content_starts: tuple[str, ...] = (),
    doc_context_max_tokens: int | None = None,
) -> list[dict[str, str]]:
    """
    Truncate a message list to fit within max_tokens.

    Truncation strategy (first → last to be cut):
      1. Low-priority system memory messages (summary, execution snapshot).
      2. doc_context (when doc_context_max_tokens is set).
      3. Older user/assistant conversation messages (earliest first).

    Messages that match *always_keep_content_starts* or have roles in
    *always_keep_roles* are never removed.
    """
    if count_messages_tokens(messages) <= max_tokens:
        return list(messages)

    result: list[dict[str, str]] = []
    kept_idx: list[int] = []

    # Pass 1: always-keep items
    for i, msg in enumerate(messages):
        role = msg.get("role", "")
        content = msg.get("content", "")
        starts_keep = any(content.startswith(p) for p in always_keep_content_starts)
        if role in always_keep_roles or starts_keep:
            result.append(msg)
            kept_idx.append(i)

    kept_tokens = count_messages_tokens(result)
    remaining_budget = max_tokens - kept_tokens
    if remaining_budget <= 0:
        return result

    # Pass 2: low-priority memory first (drop oldest of these first)
    low_priority = [
        (i, msg) for i, msg in enumerate(messages)
        if i not in kept_idx and _is_low_priority_memory(msg)
    ]
    for i, msg in low_priority:
        if remaining_budget <= 0:
            break
        msg_tokens = count_messages_tokens([msg])
        if msg_tokens <= remaining_budget:
            result.append(msg)
            kept_idx.append(i)
            remaining_budget -= msg_tokens

    # Pass 3: doc_context truncation
    if doc_context_max_tokens is not None and doc_context_max_tokens > 0:
        for i, msg in enumerate(messages):
            if i in kept_idx:
                continue
            content = msg.get("content", "")
            role = msg.get("role", "")
            # doc_context messages have role=system and their content starts
            # with the doc context label.
            if role == "system" and content.startswith("本地投研资料摘录"):
                truncated = truncate_text_to_tokens(content, doc_context_max_tokens)
                result.append({"role": role, "content": truncated})
                kept_idx.append(i)
                remaining_budget -= count_messages_tokens([{"role": role, "content": truncated}])
                break

    if remaining_budget <= 0:
        return result

    # Pass 4: remaining non-kept messages, oldest first
    remaining = [(i, msg) for i, msg in enumerate(messages) if i not in kept_idx]
    for _, msg in remaining:
        if remaining_budget <= 0:
            break
        msg_tokens = count_messages_tokens([msg])
        if msg_tokens <= remaining_budget:
            result.append(msg)
            remaining_budget -= msg_tokens

    # Re-order to original sequence
    result.sort(key=lambda m: messages.index(m) if m in messages else 999)
    return result
