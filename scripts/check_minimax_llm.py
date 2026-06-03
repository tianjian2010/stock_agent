"""Minimal live MiniMax LLM connectivity check.

This script validates that the configured OpenAI-compatible MiniMax
`base_url`, `api_key`, and `model` can complete a tiny chat request.
It intentionally does not import `app.config` so it can run without
the rest of the application's required settings such as DATABASE_URL.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

from openai import APIConnectionError, APITimeoutError, AuthenticationError, OpenAI


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_BASE_URL = "https://api.minimaxi.com/v1"
DEFAULT_MODEL = "MiniMax-M2.7"


def _load_dotenv(dotenv_path: Path) -> None:
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _mask_api_key(api_key: str) -> str:
    value = (api_key or "").strip()
    if not value:
        return "missing"
    if len(value) <= 10:
        return "set"
    return f"{value[:4]}...{value[-2:]}"


def _normalize_base_url(base_url: str) -> str:
    normalized = (base_url or "").strip()
    if not normalized:
        return DEFAULT_BASE_URL
    return normalized.rstrip("/")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check whether the configured MiniMax OpenAI-compatible chat endpoint is live."
    )
    parser.add_argument(
        "--base-url",
        default="",
        help=f"Override MINIMAX_BASE_URL. Default: {DEFAULT_BASE_URL}",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="Override MINIMAX_API_KEY.",
    )
    parser.add_argument(
        "--model",
        default="",
        help=f"Override MINIMAX_MODEL. Default: {DEFAULT_MODEL}",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=8.0,
        help="Request timeout in seconds. Default: 8",
    )
    parser.add_argument(
        "--prompt",
        default="ping",
        help="Tiny prompt used for the validation request. Default: ping",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Validate the streaming chat path instead of the normal completion path.",
    )
    return parser.parse_args()


def _build_result(*, ok: bool, category: str, message: str, **extra: Any) -> dict[str, Any]:
    return {
        "ok": ok,
        "category": category,
        "message": message,
        **extra,
    }


def run_check(args: argparse.Namespace) -> tuple[int, dict[str, Any]]:
    _load_dotenv(PROJECT_ROOT / ".env")

    api_key = (args.api_key or os.getenv("MINIMAX_API_KEY", "")).strip()
    base_url = _normalize_base_url(args.base_url or os.getenv("MINIMAX_BASE_URL", ""))
    model = (args.model or os.getenv("MINIMAX_MODEL", DEFAULT_MODEL)).strip() or DEFAULT_MODEL

    result_base = {
        "base_url": base_url,
        "model": model,
        "api_key_preview": _mask_api_key(api_key),
        "timeout_seconds": args.timeout,
    }

    if not api_key:
        return 2, _build_result(
            ok=False,
            category="missing_api_key",
            message="MINIMAX_API_KEY is missing.",
            **result_base,
        )

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        preview = ""
        if args.stream:
            stream = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": args.prompt}],
                max_tokens=8,
                temperature=0,
                extra_body={},
                timeout=args.timeout,
                stream=True,
            )
            for chunk in stream:
                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue
                delta = getattr(choices[0], "delta", None)
                text = getattr(delta, "content", None) if delta is not None else None
                if text:
                    preview += text
                if len(preview) >= 120:
                    preview = preview[:120]
                    break
        else:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": args.prompt}],
                max_tokens=8,
                temperature=0,
                extra_body={},
                timeout=args.timeout,
            )
            choices = getattr(response, "choices", None) or []
            if choices:
                preview = ((choices[0].message.content or "").strip())[:120]
        return 0, _build_result(
            ok=True,
            category="ok",
            message="MiniMax chat request succeeded." if not args.stream else "MiniMax streaming chat request succeeded.",
            response_preview=preview,
            stream=args.stream,
            **result_base,
        )
    except AuthenticationError as exc:
        return 3, _build_result(
            ok=False,
            category="invalid_api_key",
            message=str(exc),
            stream=args.stream,
            **result_base,
        )
    except APITimeoutError as exc:
        return 4, _build_result(
            ok=False,
            category="timeout",
            message=str(exc),
            stream=args.stream,
            **result_base,
        )
    except APIConnectionError as exc:
        return 5, _build_result(
            ok=False,
            category="connection_error",
            message=str(exc),
            stream=args.stream,
            **result_base,
        )
    except Exception as exc:
        message = str(exc)
        lower_message = message.lower()
        if "401" in lower_message or "invalid api key" in lower_message or "authorized_error" in lower_message:
            category = "invalid_api_key"
            exit_code = 3
        elif "timeout" in lower_message:
            category = "timeout"
            exit_code = 4
        elif "connection error" in lower_message or "dns" in lower_message or "name or service not known" in lower_message:
            category = "connection_error"
            exit_code = 5
        elif "404" in lower_message or "not found" in lower_message:
            category = "bad_base_url"
            exit_code = 6
        else:
            category = type(exc).__name__
            exit_code = 1
        return exit_code, _build_result(
            ok=False,
            category=category,
            message=message,
            stream=args.stream,
            **result_base,
        )


def main() -> int:
    args = _parse_args()
    exit_code, result = run_check(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
