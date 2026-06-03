"""End-to-end acceptance tests for the stock agent PR1 deliverables.

Covers:
1. Window stats: "最近一周提到最多的股票"
2. Daily digest: "今天研报提到了哪些股票"
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from agents.stock_agent.time_router import (
    IntentResult,
    IntentType,
    classify_intent,
)
from services.doc_fact_index import (
    DocFactIndex,
    StockMention,
    WindowStockStats,
    DailyStockSummary,
    _is_likely_stock_topic,
)


# ---------------------------------------------------------------------------
# Time router tests
# ---------------------------------------------------------------------------

class TestTimeRouter:
    def test_classify_window_stats_week_ranking(self):
        result = classify_intent("最近一周提到最多的股票有哪些")
        assert result.intent == IntentType.WINDOW_STATS
        assert result.is_stock_ranking is True
        today = date.today().isoformat()
        week_ago = (date.today() - timedelta(days=6)).isoformat()
        assert result.date_from == week_ago
        assert result.date_to == today

    def test_classify_window_stats_n_days(self):
        result = classify_intent("最近3天哪些股票被提到最多")
        assert result.intent == IntentType.WINDOW_STATS
        assert result.date_from == (date.today() - timedelta(days=2)).isoformat()

    def test_classify_window_stats_month(self):
        result = classify_intent("最近一个月研报里提到最多的前5只股票")
        assert result.intent == IntentType.WINDOW_STATS
        assert result.top_n == 5
        assert result.date_from == (date.today() - timedelta(days=29)).isoformat()

    def test_classify_daily_digest_today(self):
        result = classify_intent("今天研报有哪些内容，提到了什么股票")
        assert result.intent == IntentType.DAILY_DIGEST
        assert result.date_from == date.today().isoformat()

    def test_classify_daily_digest_yesterday(self):
        result = classify_intent("昨天研报提到了哪些股票")
        assert result.intent == IntentType.DAILY_DIGEST
        assert result.date_from == (date.today() - timedelta(days=1)).isoformat()

    def test_classify_market_state_check(self):
        result = classify_intent("中控技术603019是不是突破历史新高了")
        assert result.intent == IntentType.MARKET_STATE_CHECK
        assert "603019" in result.stock_codes

    def test_classify_market_state_trend(self):
        result = classify_intent("福瑞医科走势怎么样，上升趋势还是下降趋势")
        assert result.intent == IntentType.MARKET_STATE_CHECK

    def test_classify_cross_doc_synthesis(self):
        result = classify_intent("关于中控技术的所有研报综合看怎么评价")
        assert result.intent == IntentType.CROSS_DOC_SYNTHESIS

    def test_classify_general_qa(self):
        result = classify_intent("什么是市盈率")
        assert result.intent == IntentType.GENERAL_QA

    def test_classify_window_stats_without_ranking_falls_through(self):
        # "最近一周" without stock/ranking terms should NOT be window_stats
        result = classify_intent("最近一周的研报")
        assert result.intent != IntentType.WINDOW_STATS


# ---------------------------------------------------------------------------
# DocFactIndex tests
# ---------------------------------------------------------------------------

class TestDocFactIndex:
    @pytest.fixture
    def sample_docs(self):
        return [
            {
                "content": "中控技术（603019）业绩超预期。603019的订单增长显著。",
                "metadata": {
                    "filename": "中控技术__2026-05-10__v1.txt",
                    "topic": "中控技术",
                    "published_at": "2026-05-10",
                },
            },
            {
                "content": "福瑞医科（301235）和603019都是值得关注的标的。301235涨幅较大。",
                "metadata": {
                    "filename": "福瑞医科__2026-05-12__v1.txt",
                    "topic": "福瑞医科",
                    "published_at": "2026-05-12",
                },
            },
            {
                "content": "继续看好603019，同时关注301235的后续走势。",
                "metadata": {
                    "filename": "中控技术__2026-05-13__v1.txt",
                    "topic": "中控技术",
                    "published_at": "2026-05-13",
                },
            },
        ]

    def test_rebuild_and_top_stocks(self, sample_docs):
        index = DocFactIndex()
        result = index.rebuild(sample_docs)
        assert result["status"] == "indexed"
        assert result["documents_processed"] == 3
        assert result["unique_stocks"] == 2  # 603019, 301235

        top = index.get_top_stocks("2026-05-10", "2026-05-13", top_n=10)
        assert len(top) == 2
        # 603019: code counts 2+1+1=4, plus name "中控技术" in doc1 +1 = 5
        assert top[0].stock_code == "603019"
        assert top[0].total_mentions == 5
        assert top[0].doc_count == 3
        assert top[0].days_with_mentions == 3

        # 301235: code counts 2+1=3, plus name "福瑞医科" in doc2 +1 = 4
        assert top[1].stock_code == "301235"
        assert top[1].total_mentions == 4
        assert top[1].doc_count == 2  # doc2 + doc3

    def test_daily_summary(self, sample_docs):
        index = DocFactIndex()
        index.rebuild(sample_docs)

        summary = index.get_daily_summary("2026-05-12")
        assert summary is not None
        assert summary.total_docs_on_date == 1
        assert len(summary.stocks) == 2  # 301235 and 603019

    def test_daily_summary_empty_date(self, sample_docs):
        index = DocFactIndex()
        index.rebuild(sample_docs)

        summary = index.get_daily_summary("2026-01-01")
        assert summary is not None
        assert summary.total_docs_on_date == 0
        assert len(summary.stocks) == 0

    def test_daily_summary_counts_docs_without_stock_codes(self):
        index = DocFactIndex()
        index.rebuild(
            [
                {
                    "content": "This document has no stock code.",
                    "metadata": {
                        "filename": "theme__2026-05-18__v1.txt",
                        "topic": "theme",
                        "published_at": "2026-05-18",
                    },
                }
            ]
        )

        summary = index.get_daily_summary("2026-05-18")
        assert summary is not None
        assert summary.total_docs_on_date == 1
        assert summary.doc_count == 0
        assert summary.stocks == []

    def test_stock_timeline(self, sample_docs):
        index = DocFactIndex()
        index.rebuild(sample_docs)

        timeline = index.get_stock_timeline("603019", days=30)
        assert len(timeline) == 3  # 3 days with mentions

    def test_get_top_stocks_respects_date_range(self, sample_docs):
        index = DocFactIndex()
        index.rebuild(sample_docs)

        top = index.get_top_stocks("2026-05-12", "2026-05-13", top_n=10)
        assert len(top) == 2
        # 301235: code 2+1=3 + name "福瑞医科" in doc2 +1 = 4 in range
        assert top[0].stock_code == "301235"
        assert top[0].total_mentions == 4
        # 603019: code 1+1=2 in range
        assert top[1].stock_code == "603019"
        assert top[1].total_mentions == 2

    def test_register_stock_name(self, sample_docs):
        index = DocFactIndex()
        index.rebuild(sample_docs)
        index.register_stock_name("603019", "中控技术")
        index.register_stock_name("301235", "福瑞医科")

        top = index.get_top_stocks("2026-05-10", "2026-05-13", top_n=10)
        assert top[0].stock_name == "中控技术"
        assert top[1].stock_name == "福瑞医科"

    def test_date_range(self, sample_docs):
        index = DocFactIndex()
        index.rebuild(sample_docs)

        earliest, latest = index.get_date_range()
        assert earliest == "2026-05-10"
        assert latest == "2026-05-13"


# ---------------------------------------------------------------------------
# Topic heuristic tests
# ---------------------------------------------------------------------------

class TestTopicHeuristic:
    def test_stock_topic_positive(self):
        assert _is_likely_stock_topic("中控技术") is True
        assert _is_likely_stock_topic("福瑞医科") is True
        assert _is_likely_stock_topic("皓元医药") is True

    def test_theme_topic_negative(self):
        assert _is_likely_stock_topic("AI应用") is False
        assert _is_likely_stock_topic("宏观背景") is False
        assert _is_likely_stock_topic("3D打印") is False
        assert _is_likely_stock_topic("CoWoS") is False
        assert _is_likely_stock_topic("中东问题") is False
        assert _is_likely_stock_topic("策略周报") is False


# ---------------------------------------------------------------------------
# Market state checker tests (PR2)
# ---------------------------------------------------------------------------

class TestMarketStateChecker:
    def test_check_breakout_with_mock_data(self, monkeypatch):
        from services.market_state_checker import (
            BreakoutResult,
            MarketStateChecker,
            get_market_state_checker,
        )

        checker = MarketStateChecker()

        def mock_query(query_str):
            return {
                "data": {
                    "data": {
                        "diff": [
                            {
                                "code": "603019",
                                "name": "中控技术",
                                "f2": "45.50",
                                "f4": "3.20",
                                "f15": "46.00",
                                "f16": "44.00",
                                "f17": "44.20",
                                "f18": "44.10",
                            }
                        ]
                    }
                }
            }

        monkeypatch.setattr(checker.skill, "query", mock_query)
        # Skip period query - return day high/low
        monkeypatch.setattr(checker, "_query_period_high_low", lambda c, d: (52.0, 35.0))

        result = checker.check_breakout("603019")

        assert result.stock_code == "603019"
        assert result.stock_name == "中控技术"
        assert result.current_price == 45.50
        assert result.change_pct == 3.20
        assert result.day_high == 46.00
        assert result.day_low == 44.00
        assert result.period_high == 52.0
        assert result.period_low == 35.0
        assert not result.is_at_period_high  # 45.50 vs 52.0 = 12.5% below
        assert not result.is_at_period_low
        assert result.distance_to_high_pct == round((52.0 - 45.50) / 52.0 * 100, 2)
        assert "高点" in result.breakout_assessment or "空间" in result.breakout_assessment

    def test_check_breakout_at_high(self, monkeypatch):
        from services.market_state_checker import MarketStateChecker

        checker = MarketStateChecker()

        def mock_query(query_str):
            return {
                "data": {
                    "data": {
                        "diff": [
                            {
                                "code": "301235",
                                "name": "福瑞医科",
                                "f2": "98.50",
                                "f4": "5.00",
                                "f15": "99.00",
                                "f16": "95.00",
                                "f17": "94.00",
                                "f18": "93.80",
                            }
                        ]
                    }
                }
            }

        monkeypatch.setattr(checker.skill, "query", mock_query)
        monkeypatch.setattr(checker, "_query_period_high_low", lambda c, d: (100.0, 60.0))

        result = checker.check_breakout("301235")
        assert result.is_at_period_high  # 98.50 within 2% of 100.0
        assert "突破" in result.breakout_assessment or "接" in result.breakout_assessment

    def test_check_trend_with_mock_data(self, monkeypatch):
        from services.market_state_checker import MarketStateChecker

        checker = MarketStateChecker()

        call_count = [0]

        def mock_query(query_str):
            call_count[0] += 1
            if "最新价" in query_str:
                return {
                    "data": {
                        "data": {
                            "diff": [
                                {
                                    "code": "603019",
                                    "name": "中控技术",
                                    "f2": "45.50",
                                    "f4": "2.00",
                                }
                            ]
                        }
                    }
                }
            else:
                # MA query
                return {"data": {"data": {"diff": []}}}

        monkeypatch.setattr(checker.skill, "query", mock_query)
        monkeypatch.setattr(checker, "_query_moving_averages", lambda c: (44.0, 43.0, 41.0, 38.0))

        result = checker.check_trend("603019")

        assert result.stock_code == "603019"
        assert result.current_price == 45.50
        assert result.ma5 == 44.0
        assert result.ma10 == 43.0
        assert result.ma20 == 41.0
        assert result.ma60 == 38.0
        assert result.trend_direction == "上升趋势"  # price > all MAs + bullish alignment
        assert result.trend_strength == "强势"

    def test_check_trend_prefers_kline_data(self, monkeypatch):
        from services.market_state_checker import MarketStateChecker

        checker = MarketStateChecker()
        monkeypatch.setattr(
            checker.skill,
            "query",
            lambda _q: {
                "data": {
                    "data": {
                        "diff": [{"code": "603019", "name": "中控技术", "f2": "45.0", "f4": "1.0"}]
                    }
                }
            },
        )
        monkeypatch.setattr(
            checker.skill,
            "query_kline",
            lambda *_args, **_kwargs: {
                "data": {
                    "data": {
                        "klines": [
                            {"close": 40.0, "high": 40.5, "low": 39.5},
                            {"close": 41.0, "high": 41.5, "low": 40.5},
                            {"close": 42.0, "high": 42.5, "low": 41.5},
                            {"close": 43.0, "high": 43.5, "low": 42.5},
                            {"close": 44.0, "high": 44.5, "low": 43.5},
                            {"close": 45.0, "high": 45.5, "low": 44.5},
                        ]
                    }
                }
            },
        )

        result = checker.check_trend("603019")
        assert result.ma5 is not None
        assert result.ma5 > 0

    def test_check_trend_bearish(self, monkeypatch):
        from services.market_state_checker import MarketStateChecker

        checker = MarketStateChecker()

        def mock_query(query_str):
            return {
                "data": {
                    "data": {
                        "diff": [
                            {
                                "code": "600859",
                                "name": "测试股",
                                "f2": "35.00",
                                "f4": "-3.00",
                            }
                        ]
                    }
                }
            }

        monkeypatch.setattr(checker.skill, "query", mock_query)
        # Price below all MAs, bearish alignment (shorter < longer)
        monkeypatch.setattr(checker, "_query_moving_averages", lambda c: (46.0, 47.0, 48.0, 50.0))

        result = checker.check_trend("600859")
        assert result.trend_direction == "下降趋势"
        assert result.trend_strength == "弱势"

    def test_format_breakout_result(self):
        from services.market_state_checker import BreakoutResult, MarketStateChecker

        checker = MarketStateChecker()
        result = BreakoutResult(
            stock_code="603019",
            stock_name="中控技术",
            current_price=45.50,
            day_high=46.00,
            day_low=44.00,
            prev_close=44.10,
            change_pct=3.20,
            period_high=52.0,
            period_low=35.0,
            is_at_period_high=False,
            distance_to_high_pct=12.5,
            is_at_period_low=False,
            distance_to_low_pct=30.0,
            breakout_assessment="距周期高点有12.5%空间",
            raw_fields={},
        )

        formatted = checker.format_breakout_result(result)
        assert "603019" in formatted
        assert "中控技术" in formatted
        assert "45.50" in formatted
        assert "+3.20%" in formatted
        assert "52.0" in formatted
        assert "12.5%" in formatted

    def test_format_trend_result(self):
        from services.market_state_checker import MarketStateChecker, TrendResult

        checker = MarketStateChecker()
        result = TrendResult(
            stock_code="603019",
            stock_name="中控技术",
            current_price=45.50,
            change_pct=2.00,
            ma5=44.0,
            ma10=43.0,
            ma20=41.0,
            ma60=38.0,
            trend_direction="上升趋势",
            trend_strength="强势",
            trend_assessment="趋势方向: 上升趋势；趋势强度: 强势；MA5=44.00；MA10=43.00；MA20=41.00；MA60=38.00",
        )

        formatted = checker.format_trend_result(result)
        assert "603019" in formatted
        assert "上升趋势" in formatted
        assert "强势" in formatted
        assert "MA5" in formatted
        assert "MA20" in formatted
        assert "45.50" in formatted


class TestMarketStatePlanRouting:
    def test_trend_query_plans_market_state_tool(self):
        from agents.stock_agent.runtime import _plan_tools

        result = _plan_tools("中控技术603019是不是突破历史新高了")
        tool_names = [t.name for t in result]
        assert "mx_market_state" in tool_names

    def test_trend_query_plans_market_state_for_zoushi(self):
        from agents.stock_agent.runtime import _plan_tools

        result = _plan_tools("福瑞医科走势怎么样，均线什么情况")
        tool_names = [t.name for t in result]
        assert "mx_market_state" in tool_names

    def test_simple_price_query_still_uses_price_tool(self):
        from agents.stock_agent.runtime import _plan_tools

        result = _plan_tools("603019现在什么价格")
        tool_names = [t.name for t in result]
        assert "mx_data_price" in tool_names
        assert "mx_market_state" not in tool_names

    def test_finance_query_skips_market_state(self):
        from agents.stock_agent.runtime import _plan_tools

        result = _plan_tools("603019市盈率多少")
        tool_names = [t.name for t in result]
        assert "mx_market_state" not in tool_names
        assert any("finance" in n for n in tool_names)
