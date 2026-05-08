"""MiniMax-compatible LLM service wrappers built on the OpenAI client."""

import logging
from dataclasses import dataclass
from typing import Any

import requests
from openai import AsyncOpenAI, OpenAI

from app.config import (
    EMBEDDING_API_KEY,
    EMBEDDING_BASE_URL,
    EMBEDDING_PROVIDER,
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
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
        return "https://api.minimax.io/v1"
    # Older configs mistakenly used minimaxi.com; normalize to the official endpoint.
    return normalized.replace("api.minimaxi.com", "api.minimax.io")


@dataclass(slots=True)
class ChatResult:
    content: str


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
        client_kwargs = {
            "api_key": _require_api_key(),
            "base_url": _normalize_minimax_base_url(MINIMAX_BASE_URL),
        }
        self.client = OpenAI(**client_kwargs)
        self.async_client = AsyncOpenAI(**client_kwargs)

    def invoke(self, messages: list[Any]) -> ChatResult:
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=self._normalize_messages(messages),
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                extra_body=self._build_extra_body(),
            )
        except Exception as exc:
            logger.error(
                "LLM invoke failed: model=%s, temperature=%s, max_tokens=%s, thinking=%s, error=%s",
                self.model, self.temperature, self.max_tokens, self.thinking_enabled, exc,
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
        try:
            response = await self.async_client.chat.completions.create(
                model=self.model,
                messages=self._normalize_messages(messages),
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                extra_body=self._build_extra_body(),
            )
        except Exception as exc:
            logger.error(
                "LLM ainvoke failed: model=%s, temperature=%s, max_tokens=%s, thinking=%s, error=%s",
                self.model, self.temperature, self.max_tokens, self.thinking_enabled, exc,
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
        try:
            return self.client.chat.completions.create(
                model=self.model,
                messages=self._normalize_messages(messages),
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                extra_body=self._build_extra_body(),
                stream=True,
            )
        except Exception as exc:
            logger.error(
                "LLM stream failed: model=%s, temperature=%s, max_tokens=%s, thinking=%s, error=%s",
                self.model, self.temperature, self.max_tokens, self.thinking_enabled, exc,
            )
            raise

    async def astream(self, messages: list[Any]) -> Any:
        """Async streaming chat completion yielding deltas."""
        try:
            async for chunk in await self.async_client.chat.completions.create(
                model=self.model,
                messages=self._normalize_messages(messages),
                temperature=self.temperature,
                max_tokens=self.max_tokens,
                extra_body=self._build_extra_body(),
                stream=True,
            ):
                yield chunk
        except Exception as exc:
            logger.error(
                "LLM astream failed: model=%s, temperature=%s, max_tokens=%s, thinking=%s, error=%s",
                self.model, self.temperature, self.max_tokens, self.thinking_enabled, exc,
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
                f"({self.describe()}, status={self._extract_status_code(exc)}, error={self._extract_error_text(exc)})"
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
                f"({self.describe()}, status={self._extract_status_code(exc)}, error={self._extract_error_text(exc)})"
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
    def _extract_status_code(exc: Exception) -> Any:
        status_code = getattr(exc, "status_code", None)
        if status_code is not None:
            return status_code
        response = getattr(exc, "response", None)
        return getattr(response, "status_code", "unknown")

    @staticmethod
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
