"""Live title-generation probe for the configured MiniMax chat model.

Runs the exact sidebar-title prompt path against the real LLM without mocks,
then prints:
1. raw model response
2. extracted title
3. heuristic fallback title

This script intentionally avoids importing app.config directly so it can run
as a focused diagnostic without booting the whole app stack.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.stock_agent.agent import (  # noqa: E402
    TITLE_SYSTEM_PROMPT,
    _extract_answer,
    _extract_title_from_response,
    _heuristic_title_from_query,
)
from services.llm import create_stock_chat, describe_minimax_chat_config  # noqa: E402


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


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a live LLM title-generation probe.")
    parser.add_argument(
        "--query",
        default="福瑞医科最近几篇资料综合看，经营边际变化是什么",
        help="User query to turn into a sidebar title.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=48,
        help="Max tokens for the title-generation request.",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="How many times to run the same prompt.",
    )
    return parser.parse_args()


def run_once(query: str, max_tokens: int) -> dict[str, str]:
    chat = create_stock_chat(temperature=0.0, max_tokens=max_tokens, thinking_enabled=False)
    response = chat.invoke(
        [
            {"role": "system", "content": TITLE_SYSTEM_PROMPT},
            {"role": "user", "content": query.strip()},
        ]
    )
    raw = response.content or ""
    text = _extract_answer(raw)
    extracted = _extract_title_from_response(text)
    fallback = _heuristic_title_from_query(query)
    final = extracted or fallback
    return {
        "query": query,
        "raw_response": raw,
        "cleaned_response": text,
        "extracted_title": extracted,
        "fallback_title": fallback,
        "final_title": final,
    }


def main() -> int:
    _load_dotenv(PROJECT_ROOT / ".env")
    args = _parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    result = {
        "config": describe_minimax_chat_config(),
        "runs": [run_once(args.query, args.max_tokens) for _ in range(max(1, args.repeat))],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
