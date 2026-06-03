"""Time-aware intent router for stock agent queries.

Classifies user queries into intent types so the agent can route to the
correct execution path (structured aggregation vs vector retrieval vs tool calls).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from typing import Any


class IntentType(str, Enum):
    DAILY_DIGEST = "daily_digest"           # "今天研报有哪些/提到什么股票"
    WINDOW_STATS = "window_stats"           # "最近一周提到最多的股票"
    CROSS_DOC_SYNTHESIS = "cross_doc_synthesis"  # "关于XX的所有研报怎么评价"
    MARKET_STATE_CHECK = "market_state_check"    # "XX股是否突破新高/走势"
    GENERAL_QA = "general_qa"               # fallback


@dataclass(slots=True)
class IntentResult:
    intent: IntentType
    date_from: str  # ISO date for window start (window_stats) or target date (daily_digest)
    date_to: str    # ISO date for window end
    stock_codes: list[str]
    stock_keywords: list[str]
    top_n: int      # for "top N" ranking queries
    is_stock_ranking: bool  # "最多/排名/前N" semantics


STOCK_CODE_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")

# "today" relative date patterns
_TODAY_TERMS = ("今天", "今日", "当天", "本日")
_YESTERDAY_TERMS = ("昨天", "昨日")

# Chinese number mapping for window patterns
_CN_NUM = {"一": 1, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}

# window patterns: "最近N天/周/月" (digit or Chinese number)
_WINDOW_PATTERN = re.compile(
    r"最近(?:(?P<num_digit>\d+)|(?P<num_cn>[一-九十]+))?\s*(?P<unit>天|日|周|个?月)"
)
_WINDOW_KEYWORDS = ("最近", "近几", "近一", "近两", "近三")

# ranking patterns
_RANKING_TERMS = ("最多", "排名", "前", "top", "Top", "TOP", "排前", "最热", "最受关注")
_STOCK_LIST_TERMS = ("哪些股票", "什么股票", "哪只股票", "哪几只", "个股", "标的", "提到")

# digest patterns
_DIGEST_TERMS = ("有哪些", "什么内容", "讲了什么", "有哪些内容", "提到什么")

# market state patterns
_MARKET_STATE_TERMS = (
    "突破", "新高", "新低", "走势", "趋势", "均线",
    "最高价", "最低价", "涨势", "跌势", "震荡", "回调", "反弹",
    "支撑位", "压力位", "压力", "支撑", "技术面", "K线",
)

# cross-doc synthesis patterns
_SYNTHESIS_TERMS = ("综合看", "总结", "归纳", "梳理", "对比", "共同点", "怎么看", "评价")


def classify_intent(query: str) -> IntentResult:
    """Classify a user query into an intent type with extracted parameters."""
    q = query.strip()

    stock_codes = sorted(set(STOCK_CODE_RE.findall(q)))
    window_match = _WINDOW_PATTERN.search(q)
    has_window_keyword = any(kw in q for kw in _WINDOW_KEYWORDS)
    has_ranking = any(term in q for term in _RANKING_TERMS)
    has_stock_list = any(term in q for term in _STOCK_LIST_TERMS)
    has_digest = any(term in q for term in _DIGEST_TERMS)
    has_market_state = any(term in q for term in _MARKET_STATE_TERMS)
    has_synthesis = any(term in q for term in _SYNTHESIS_TERMS)
    has_today = any(term in q for term in _TODAY_TERMS)
    has_yesterday = any(term in q for term in _YESTERDAY_TERMS)

    today = date.today().isoformat()

    # 1. Daily digest: "今天研报有哪些/提到什么股票"
    if has_today and (has_digest or has_stock_list):
        return IntentResult(
            intent=IntentType.DAILY_DIGEST,
            date_from=today,
            date_to=today,
            stock_codes=stock_codes,
            stock_keywords=_extract_stock_keywords(q),
            top_n=10,
            is_stock_ranking=has_ranking,
        )

    if has_yesterday and (has_digest or has_stock_list):
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        return IntentResult(
            intent=IntentType.DAILY_DIGEST,
            date_from=yesterday,
            date_to=yesterday,
            stock_codes=stock_codes,
            stock_keywords=_extract_stock_keywords(q),
            top_n=10,
            is_stock_ranking=has_ranking,
        )

    # 2. Window stats: "最近一周/3天/一个月提到最多的股票"
    if (has_window_keyword or window_match) and (has_ranking or has_stock_list):
        days = _resolve_window_days(window_match)
        date_to = today
        date_from = (date.today() - timedelta(days=max(days - 1, 0))).isoformat()
        top_n = _extract_top_n(q, default=10)
        return IntentResult(
            intent=IntentType.WINDOW_STATS,
            date_from=date_from,
            date_to=date_to,
            stock_codes=stock_codes,
            stock_keywords=_extract_stock_keywords(q),
            top_n=top_n,
            is_stock_ranking=True,
        )

    # 3. Market state check: "XX突破新高/走势/趋势" + stock code or name
    if has_market_state and (stock_codes or _has_stock_name_pattern(q)):
        return IntentResult(
            intent=IntentType.MARKET_STATE_CHECK,
            date_from="",
            date_to="",
            stock_codes=stock_codes,
            stock_keywords=_extract_stock_keywords(q),
            top_n=0,
            is_stock_ranking=False,
        )

    # 4. Cross-doc synthesis: default for research/analysis queries
    if has_synthesis:
        return IntentResult(
            intent=IntentType.CROSS_DOC_SYNTHESIS,
            date_from="",
            date_to="",
            stock_codes=stock_codes,
            stock_keywords=_extract_stock_keywords(q),
            top_n=0,
            is_stock_ranking=False,
        )

    # 5. General QA
    return IntentResult(
        intent=IntentType.GENERAL_QA,
        date_from="",
        date_to="",
        stock_codes=stock_codes,
        stock_keywords=_extract_stock_keywords(q),
        top_n=0,
        is_stock_ranking=False,
    )


def _resolve_window_days(match: re.Match | None) -> int:
    """Convert a window pattern match to a day count."""
    if match is None:
        return 7  # default: 1 week

    num = 1  # default if no explicit number (e.g. "最近个月" → treat as 1)
    num_digit = match.group("num_digit")
    num_cn = match.group("num_cn")
    unit = match.group("unit") or ""

    if num_digit:
        num = int(num_digit)
    elif num_cn:
        num = _CN_NUM.get(num_cn, 1)

    if "月" in unit:
        return num * 30
    if "周" in unit:
        return num * 7
    return num  # days


def _extract_top_n(query: str, default: int = 10) -> int:
    m = re.search(r"(?:前|top|Top|TOP)\s*(\d+)", query)
    if m:
        return int(m.group(1))
    return default


def _extract_stock_keywords(query: str) -> list[str]:
    """Extract potential stock name substrings from query."""
    # Remove common question words
    noise = re.compile(
        r"最近|一周|今天|昨天|今日|昨日|研报|报告|资料|文档|提到|哪些|什么|怎么|如何"
        r"|最多|排名|第几|个股|标的|股票|走势|趋势|突破|新高|新低|怎么样|有没有"
        r"|前\d+|top\d+"
    )
    cleaned = noise.sub(" ", query)
    # Extract Chinese word candidates (2-6 chars)
    words = re.findall(r"[一-鿿]{2,6}", cleaned)
    return [w for w in words if len(w) >= 2]


def _has_stock_name_pattern(query: str) -> bool:
    """Check if query contains patterns that look like stock names."""
    # Remove known non-stock terms
    noise = re.compile(
        r"最近|一周|今天|昨天|研报|报告|资料|文档|提到|哪些|什么|怎么|如何"
        r"|最多|排名|个股|标的|股票|走势|趋势|突破|新高|新低|怎么样|有没有|支撑"
    )
    cleaned = noise.sub(" ", query)
    return bool(re.search(r"[一-鿿]{2,6}", cleaned))
