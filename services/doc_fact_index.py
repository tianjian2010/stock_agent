"""Document fact index for stock mention aggregation and time-window queries.

Provides structured, verifiable answers to questions like:
- "最近一周提到最多的股票有哪些"
- "今天研报提到了哪些股票"
- "中控技术在最近研报中出现频率"
"""

from __future__ import annotations

import json
import logging
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

from app.config import DOC_FACT_INDEX_PATH, ETF_CODE_PREFIXES, NON_STOCK_TOPIC_PATTERNS, STOCK_NAME_CACHE_PATH

logger = logging.getLogger(__name__)

STOCK_CODE_PATTERN = re.compile(r"(?<!\d)(\d{6})(?!\d)")


def _is_etf_or_fund_code(code: str) -> bool:
    """Check if a 6-digit code belongs to an ETF / fund rather than an individual stock."""
    return code.startswith(ETF_CODE_PREFIXES)


def _is_likely_stock_topic(topic: str) -> bool:
    """Heuristic: does a document topic look like a stock name rather than a theme/concept?"""
    if not topic:
        return False
    for pattern in NON_STOCK_TOPIC_PATTERNS:
        if pattern.lower() in topic.lower():
            return False
    # Stock names are typically 2-6 Chinese characters with no digits/english
    if re.match(r"^[一-鿿]{2,8}$", topic):
        return True
    return False


def _classify_mention_type(stock_code: str) -> str:
    """Classify a mention as 'stock', 'etf', or 'concept'."""
    if stock_code.startswith("NAME:"):
        return "concept"
    if _is_etf_or_fund_code(stock_code):
        return "etf"
    return "stock"


@dataclass(slots=True)
class StockMention:
    stock_code: str
    doc_date: str
    mention_count: int
    mention_type: str = "stock"  # "stock" | "etf" | "concept"


@dataclass(slots=True)
class WindowStockStats:
    stock_code: str
    stock_name: str
    total_mentions: int
    doc_count: int
    days_with_mentions: int


@dataclass(slots=True)
class DailyStockSummary:
    date: str
    doc_count: int
    total_docs_on_date: int
    stocks: list[dict[str, Any]]


class DocFactIndex:
    """Tracks stock-code mentions per document for time-window aggregation."""

    def __init__(self) -> None:
        self._mentions: dict[str, list[StockMention]] = {}  # doc_filename -> mentions
        self._doc_dates: dict[str, str] = {}  # doc_filename -> published_at (all docs)
        self._stock_name_map: dict[str, str] = {}  # code -> name
        self._known_topics: set[str] = set()  # doc topics that are stock names
        self._ready = False

    # ------------------------------------------------------------------
    # Build
    # ------------------------------------------------------------------

    def rebuild(self, documents: list[dict[str, Any]]) -> dict[str, Any]:
        """Full rebuild: pass-1 extracts codes + known topics, pass-2 scans name mentions."""
        self._mentions = {}
        self._doc_dates = {}
        self._known_topics = set()
        self._name_to_code: dict[str, str] = {}  # topic name -> best-guess stock code
        self._load_stock_name_cache()

        # Pass 1: extract codes and build known topics
        for doc in documents:
            self._extract_codes(doc)

        # Build name->code hints from co-occurrence in documents
        self._build_name_code_hints(documents)

        # Pass 2: scan for known stock names in all documents
        for doc in documents:
            self._extract_names(doc)

        self._ready = True
        self._save()
        self._save_stock_name_cache()

        unique_ids = set()
        for mentions in self._mentions.values():
            for m in mentions:
                unique_ids.add(m.stock_code)

        return {
            "status": "indexed",
            "documents_processed": len(documents),
            "documents_with_mentions": len(self._mentions),
            "total_stock_mentions": sum(
                len(v) for v in self._mentions.values()
            ),
            "unique_stocks": len(unique_ids),
            "known_stock_topics": len(self._known_topics),
        }

    def _extract_codes(self, doc: dict[str, Any]) -> None:
        """Pass 1: extract 6-digit stock codes and record known topics."""
        content = doc.get("content", "")
        metadata = doc.get("metadata", {})
        filename = metadata.get("filename", "")
        topic = metadata.get("topic", "")
        published_at = metadata.get("published_at", "")

        if not filename or not published_at or not content:
            return

        self._doc_dates[filename] = published_at

        mentions: list[StockMention] = []

        codes = STOCK_CODE_PATTERN.findall(content)
        if codes:
            code_counts = Counter(codes)
            for code, count in code_counts.items():
                mtype = _classify_mention_type(code)
                mentions.append(
                    StockMention(
                        stock_code=code,
                        doc_date=published_at,
                        mention_count=count,
                        mention_type=mtype,
                    )
                )

        if _is_likely_stock_topic(topic):
            self._known_topics.add(topic)

        if mentions:
            self._mentions[filename] = mentions

    def _build_name_code_hints(self, documents: list[dict[str, Any]]) -> None:
        """Infer stock code for topic names by checking co-occurrence in docs."""
        for doc in documents:
            content = doc.get("content", "")
            metadata = doc.get("metadata", {})
            topic = metadata.get("topic", "")
            if not _is_likely_stock_topic(topic):
                continue

            codes_in_doc = STOCK_CODE_PATTERN.findall(content)
            if codes_in_doc and topic in content:
                self._name_to_code[topic] = codes_in_doc[0]
                self._stock_name_map[codes_in_doc[0]] = topic

    def _extract_names(self, doc: dict[str, Any]) -> None:
        """Pass 2: scan document text for known stock topic names."""
        content = doc.get("content", "")
        metadata = doc.get("metadata", {})
        filename = metadata.get("filename", "")
        published_at = metadata.get("published_at", "")

        if not filename or not published_at or not content or not self._known_topics:
            return

        existing = self._mentions.get(filename, [])
        existing_codes = {m.stock_code for m in existing}

        for name in self._known_topics:
            count = content.count(name)
            if count == 0:
                continue
            # Resolve code: use hint mapping, or fall back to name itself
            resolved_code = self._name_to_code.get(name, f"NAME:{name}")
            mtype = _classify_mention_type(resolved_code)
            if resolved_code in existing_codes:
                # Merge: add to existing code-based mention count
                for m in existing:
                    if m.stock_code == resolved_code:
                        m.mention_count += count
                        break
            else:
                existing.append(
                    StockMention(
                        stock_code=resolved_code,
                        doc_date=published_at,
                        mention_count=count,
                        mention_type=mtype,
                    )
                )
                existing_codes.add(resolved_code)

        if existing:
            self._mentions[filename] = existing

    def register_stock_name(self, code: str, name: str) -> None:
        self._stock_name_map[code] = name

    def register_stock_names(self, mapping: dict[str, str]) -> None:
        self._stock_name_map.update(mapping)

    # ------------------------------------------------------------------
    # Query
    # ------------------------------------------------------------------

    def get_top_stocks(
        self, date_from: str, date_to: str, top_n: int = 10
    ) -> list[WindowStockStats]:
        """Top mentioned stocks in a date range [date_from, date_to]."""
        self._ensure_ready()

        stats: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"total_mentions": 0, "doc_count": 0, "days": set()}
        )

        for filename, mentions in self._mentions.items():
            for m in mentions:
                if date_from <= m.doc_date <= date_to:
                    s = stats[m.stock_code]
                    s["total_mentions"] += m.mention_count
                    s["doc_count"] += 1
                    s["days"].add(m.doc_date)

        results = []
        for code, s in sorted(
            stats.items(), key=lambda x: x[1]["total_mentions"], reverse=True
        )[:top_n]:
            display_code = code
            display_name = self._stock_name_map.get(code, "")
            if code.startswith("NAME:"):
                display_code = ""
                display_name = code[5:]
            results.append(
                WindowStockStats(
                    stock_code=display_code,
                    stock_name=display_name,
                    total_mentions=s["total_mentions"],
                    doc_count=s["doc_count"],
                    days_with_mentions=len(s["days"]),
                )
            )

        return results

    def get_daily_summary(self, target_date: str) -> DailyStockSummary:
        """Stock mention summary for a specific date."""
        self._ensure_ready()

        stocks: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"mentions": 0, "doc_count": 0, "mention_type": "stock"}
        )
        docs_with_stocks: set[str] = set()
        all_docs_on_date: set[str] = {
            filename for filename, doc_date in self._doc_dates.items() if doc_date == target_date
        }

        for filename, mentions in self._mentions.items():
            for m in mentions:
                if m.doc_date == target_date:
                    s = stocks[m.stock_code]
                    s["mentions"] += m.mention_count
                    s["doc_count"] += 1
                    s["mention_type"] = m.mention_type
                    docs_with_stocks.add(filename)

        if not docs_with_stocks:
            return DailyStockSummary(
                date=target_date,
                doc_count=0,
                total_docs_on_date=len(all_docs_on_date),
                stocks=[],
            )

        stock_list = sorted(
            [
                {
                    "stock_code": "" if code.startswith("NAME:") else code,
                    "stock_name": code[5:] if code.startswith("NAME:") else self._stock_name_map.get(code, ""),
                    "mentions": s["mentions"],
                    "doc_count": s["doc_count"],
                    "mention_type": s["mention_type"],
                }
                for code, s in stocks.items()
            ],
            key=lambda x: x["mentions"],
            reverse=True,
        )

        return DailyStockSummary(
            date=target_date,
            doc_count=len(docs_with_stocks),
            total_docs_on_date=len(all_docs_on_date),
            stocks=stock_list,
        )

    def get_stock_timeline(
        self, stock_code: str, days: int = 30
    ) -> list[dict[str, Any]]:
        """Per-day mention counts for a stock over the last N days."""
        self._ensure_ready()

        cutoff = (date.today() - timedelta(days=days)).isoformat()
        day_counts: dict[str, int] = defaultdict(int)

        for filename, mentions in self._mentions.items():
            for m in mentions:
                if m.stock_code == stock_code and m.doc_date >= cutoff:
                    day_counts[m.doc_date] += m.mention_count

        return sorted(
            [
                {"date": d, "mention_count": c}
                for d, c in day_counts.items()
            ],
            key=lambda x: x["date"],
        )

    def get_date_range(self) -> tuple[str, str]:
        """Return (earliest_date, latest_date) across all indexed mentions."""
        self._ensure_ready()
        dates = sorted({
            m.doc_date
            for mentions in self._mentions.values()
            for m in mentions
        })
        if not dates:
            return ("", "")
        return dates[0], dates[-1]

    def get_known_stock_topics(self) -> set[str]:
        self._ensure_ready()
        return self._known_topics.copy()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _ensure_ready(self) -> None:
        if not self._ready:
            self._load()

    def _save(self) -> None:
        DOC_FACT_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
        payload: dict[str, Any] = {
            "mentions": {
                filename: [
                    {
                        "stock_code": m.stock_code,
                        "doc_date": m.doc_date,
                        "mention_count": m.mention_count,
                        "mention_type": m.mention_type,
                    }
                    for m in mentions
                ]
                for filename, mentions in self._mentions.items()
            },
            "doc_dates": self._doc_dates,
            "name_to_code": self._name_to_code,
            "known_topics": sorted(self._known_topics),
        }
        try:
            with open(DOC_FACT_INDEX_PATH, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("Failed to save doc fact index: %s", exc)

    def _load(self) -> None:
        if not DOC_FACT_INDEX_PATH.exists():
            self._ready = True
            return
        try:
            with open(DOC_FACT_INDEX_PATH, "r", encoding="utf-8") as f:
                payload = json.load(f)
        except Exception as exc:
            logger.warning("Failed to load doc fact index: %s", exc)
            self._ready = True
            return

        self._mentions = {}
        for filename, raw_mentions in payload.get("mentions", {}).items():
            self._mentions[filename] = [
                StockMention(
                    stock_code=m["stock_code"],
                    doc_date=m["doc_date"],
                    mention_count=m["mention_count"],
                    mention_type=m.get("mention_type", _classify_mention_type(m["stock_code"])),
                )
                for m in raw_mentions
            ]
        self._doc_dates = {
            str(filename): str(doc_date)
            for filename, doc_date in payload.get("doc_dates", {}).items()
            if filename and doc_date
        }
        self._name_to_code = {
            str(k): str(v)
            for k, v in payload.get("name_to_code", {}).items()
        }
        self._known_topics = set(payload.get("known_topics", []))
        self._load_stock_name_cache()
        self._ready = True

    def _load_stock_name_cache(self) -> None:
        if not STOCK_NAME_CACHE_PATH.exists():
            return
        try:
            with open(STOCK_NAME_CACHE_PATH, "r", encoding="utf-8") as f:
                self._stock_name_map = json.load(f)
        except Exception:
            pass

    def _save_stock_name_cache(self) -> None:
        if not self._stock_name_map:
            return
        STOCK_NAME_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        try:
            with open(STOCK_NAME_CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(self._stock_name_map, f, ensure_ascii=False, indent=2)
        except Exception as exc:
            logger.warning("Failed to save stock name cache: %s", exc)


_doc_fact_index: DocFactIndex | None = None


def get_doc_fact_index() -> DocFactIndex:
    global _doc_fact_index
    if _doc_fact_index is None:
        _doc_fact_index = DocFactIndex()
    return _doc_fact_index
