"""Market state checker for breakout detection and trend analysis."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from skills.mx_data import get_mx_data_skill

logger = logging.getLogger(__name__)

DIFF_FIELD_MAP = {
    "f2": "latest_price",
    "f3": "change_amount",
    "f4": "change_pct",
    "f15": "day_high",
    "f16": "day_low",
    "f17": "open",
    "f18": "prev_close",
    "f20": "total_market_cap",
    "f21": "float_market_cap",
    "f8": "turnover_rate",
    "f9": "pe_ratio",
}


@dataclass(slots=True)
class BreakoutResult:
    stock_code: str
    stock_name: str
    current_price: float
    day_high: float
    day_low: float
    prev_close: float
    change_pct: float
    period_high: float
    period_low: float
    is_at_period_high: bool
    distance_to_high_pct: float
    is_at_period_low: bool
    distance_to_low_pct: float
    breakout_assessment: str
    period_label: str = "近1年"
    raw_fields: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TrendResult:
    stock_code: str
    stock_name: str
    current_price: float
    change_pct: float
    ma5: float | None = None
    ma10: float | None = None
    ma20: float | None = None
    ma60: float | None = None
    trend_direction: str = ""
    trend_strength: str = ""
    trend_assessment: str = ""
    raw_fields: dict[str, Any] = field(default_factory=dict)


class MarketStateChecker:
    """Analyzes market state for breakout and trend using quote + kline data."""

    def __init__(self) -> None:
        self.skill = get_mx_data_skill()

    def check_breakout(self, stock_code: str, *, extended: bool = False) -> BreakoutResult:
        raw = self._query_price(stock_code)
        fields = self._extract_diff_fields(raw)
        name = fields.get("name", "") or stock_code

        current = self._float_or(fields.get("latest_price"), 0.0)
        day_high = self._float_or(fields.get("day_high"), current)
        day_low = self._float_or(fields.get("day_low"), current)
        prev_close = self._float_or(fields.get("prev_close"), current)
        change_pct = self._float_or(fields.get("change_pct"), 0.0)

        kline_count = 1200 if extended else 260
        period_label = "近5年" if extended else "近1年"
        period_high, period_low = self._query_period_high_low(stock_code, raw, count=kline_count)

        dist_to_high = ((period_high - current) / period_high * 100) if period_high > 0 else 0.0
        dist_to_low = ((current - period_low) / period_low * 100) if period_low > 0 else 0.0
        at_high = dist_to_high <= 2.0
        at_low = dist_to_low <= 2.0

        assessment = self._assess_breakout(
            current=current,
            period_high=period_high,
            period_low=period_low,
            distance_high=dist_to_high,
            distance_low=dist_to_low,
            change_pct=change_pct,
        )

        return BreakoutResult(
            stock_code=stock_code,
            stock_name=name,
            current_price=current,
            day_high=day_high,
            day_low=day_low,
            prev_close=prev_close,
            change_pct=change_pct,
            period_high=period_high,
            period_low=period_low,
            is_at_period_high=at_high,
            distance_to_high_pct=round(dist_to_high, 2),
            is_at_period_low=at_low,
            distance_to_low_pct=round(dist_to_low, 2),
            breakout_assessment=assessment,
            period_label=period_label,
            raw_fields=fields,
        )

    def check_trend(self, stock_code: str) -> TrendResult:
        raw = self._query_price(stock_code)
        fields = self._extract_diff_fields(raw)
        name = fields.get("name", "") or stock_code

        current = self._float_or(fields.get("latest_price"), 0.0)
        change_pct = self._float_or(fields.get("change_pct"), 0.0)
        ma5, ma10, ma20, ma60 = self._query_moving_averages(stock_code)

        direction, strength = self._assess_trend(current, ma5, ma10, ma20, ma60)
        parts: list[str] = []
        if direction:
            parts.append(f"趋势方向: {direction}")
        if strength:
            parts.append(f"趋势强度: {strength}")
        if ma5 is not None:
            parts.append(f"MA5={ma5:.2f}")
        if ma10 is not None:
            parts.append(f"MA10={ma10:.2f}")
        if ma20 is not None:
            parts.append(f"MA20={ma20:.2f}")
        if ma60 is not None:
            parts.append(f"MA60={ma60:.2f}")

        return TrendResult(
            stock_code=stock_code,
            stock_name=name,
            current_price=current,
            change_pct=change_pct,
            ma5=ma5,
            ma10=ma10,
            ma20=ma20,
            ma60=ma60,
            trend_direction=direction,
            trend_strength=strength,
            trend_assessment="；".join(parts) if parts else "无法获取足够的趋势数据",
            raw_fields=fields,
        )

    def format_breakout_result(self, result: BreakoutResult) -> str:
        lines = [
            f"突破分析 - {result.stock_code} {result.stock_name}",
            f"  现价: {result.current_price:.2f}",
            f"  涨跌幅: {result.change_pct:+.2f}%",
            f"  今日高/低: {result.day_high:.2f} / {result.day_low:.2f}",
        ]
        if result.period_high > 0:
            lines.append(f"  {result.period_label}最高: {result.period_high:.2f} (距高点 {result.distance_to_high_pct:.2f}%)")
        if result.period_low > 0:
            lines.append(f"  {result.period_label}最低: {result.period_low:.2f} (距低点 {result.distance_to_low_pct:.2f}%)")
        lines.append(f"  突破阈值: 距高点≤2%视为逼近突破区域，当前{'在' if result.is_at_period_high else '不在'}阈值内")
        lines.append(f"  研判: {result.breakout_assessment}")
        return "\n".join(lines)

    def format_trend_result(self, result: TrendResult) -> str:
        lines = [
            f"趋势分析 - {result.stock_code} {result.stock_name}",
            f"  现价: {result.current_price:.2f} ({result.change_pct:+.2f}%)",
        ]
        if result.ma5 is not None:
            lines.append(f"  MA5:  {result.ma5:.2f}")
        if result.ma10 is not None:
            lines.append(f"  MA10: {result.ma10:.2f}")
        if result.ma20 is not None:
            lines.append(f"  MA20: {result.ma20:.2f}")
        if result.ma60 is not None:
            lines.append(f"  MA60: {result.ma60:.2f}")
        lines.append(f"  研判: {result.trend_assessment}")
        return "\n".join(lines)

    def _query_price(self, stock_code: str) -> dict[str, Any]:
        return self.skill.query(f"{stock_code} 最新价 最高 最低 涨跌幅")

    def _query_period_high_low(
        self,
        stock_code: str,
        price_data: dict[str, Any],
        *,
        count: int = 260,
    ) -> tuple[float, float]:
        fields = self._extract_diff_fields(price_data)
        day_high = self._float_or(fields.get("day_high"), 0.0)
        day_low = self._float_or(fields.get("day_low"), 0.0)

        try:
            kline_rows = self._extract_kline_series(
                self.skill.query_kline(stock_code, period="day", count=count)
            )
        except Exception as exc:
            logger.debug("Kline period query failed: %s", exc)
            kline_rows = []
        if kline_rows:
            highs = [row["high"] for row in kline_rows if row.get("high") is not None]
            lows = [row["low"] for row in kline_rows if row.get("low") is not None]
            if highs and lows:
                return max(highs), min(lows)

        return day_high, day_low

    def _query_moving_averages(self, stock_code: str) -> tuple[float | None, float | None, float | None, float | None]:
        try:
            kline_rows = self._extract_kline_series(
                self.skill.query_kline(stock_code, period="day", count=120)
            )
        except Exception as exc:
            logger.debug("Kline MA query failed: %s", exc)
            kline_rows = []
        if kline_rows:
            closes = [row["close"] for row in kline_rows if row.get("close") is not None]
            return (
                self._moving_average(closes, 5),
                self._moving_average(closes, 10),
                self._moving_average(closes, 20),
                self._moving_average(closes, 60),
            )

        try:
            raw = self.skill.query(f"{stock_code} 均线 MA5 MA10 MA20 MA60 技术指标")
            fields = self._extract_diff_fields(raw)
            ma5 = self._float_or_none(fields.get("ma5"))
            ma10 = self._float_or_none(fields.get("ma10"))
            ma20 = self._float_or_none(fields.get("ma20"))
            ma60 = self._float_or_none(fields.get("ma60"))
            return ma5, ma10, ma20, ma60
        except Exception as exc:
            logger.debug("Fallback MA query failed: %s", exc)
            return None, None, None, None

    @staticmethod
    def _moving_average(values: list[float], window: int) -> float | None:
        if window <= 0 or len(values) < window:
            return None
        segment = values[-window:]
        return sum(segment) / window

    @staticmethod
    def _extract_kline_series(data: dict[str, Any]) -> list[dict[str, float | None]]:
        rows = data.get("data", {}).get("data", {}).get("klines", [])
        parsed: list[dict[str, float | None]] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            parsed.append(
                {
                    "close": MarketStateChecker._float_or_none(row.get("close")),
                    "high": MarketStateChecker._float_or_none(row.get("high")),
                    "low": MarketStateChecker._float_or_none(row.get("low")),
                }
            )
        return parsed

    @staticmethod
    def _extract_diff_fields(data: dict[str, Any]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        try:
            inner = data.get("data", {})
            diff_rows = inner.get("data", {}).get("diff", [])
            for row in diff_rows:
                code = row.get("code", "")
                if code:
                    result.setdefault("code", code)
                name = row.get("name", "")
                if name:
                    result.setdefault("name", name)
                for raw_key, mapped in DIFF_FIELD_MAP.items():
                    val = row.get(raw_key)
                    if val is not None and val != "-" and val != "":
                        result.setdefault(mapped, val)
        except Exception as exc:
            logger.debug("Failed to extract diff fields: %s", exc)
        return result

    @staticmethod
    def _float_or(value: Any, default: float) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    @staticmethod
    def _float_or_none(value: Any) -> float | None:
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _assess_breakout(
        *,
        current: float,
        period_high: float,
        period_low: float,
        distance_high: float,
        distance_low: float,
        change_pct: float,
    ) -> str:
        parts: list[str] = []
        if period_high > 0:
            if distance_high <= 2.0 and change_pct > 0:
                parts.append(f"正在逼近或突破高点，距高点 {distance_high:.1f}%")
            elif distance_high <= 5.0:
                parts.append(f"靠近高位，距高点 {distance_high:.1f}%")
            else:
                parts.append(f"距高点仍有 {distance_high:.1f}% 空间")
        if period_low > 0 and distance_low <= 2.0:
            parts.append(f"接近低位，距低点 {distance_low:.1f}%")
        if not parts:
            return "无法获取完整的高低点区间数据"
        return "；".join(parts)

    @staticmethod
    def _assess_trend(
        current: float,
        ma5: float | None,
        ma10: float | None,
        ma20: float | None,
        ma60: float | None,
    ) -> tuple[str, str]:
        mas = [v for v in [ma5, ma10, ma20, ma60] if v is not None]
        if len(mas) < 2:
            return "", ""

        above_count = sum(1 for v in mas if current > v)
        below_count = len(mas) - above_count
        bullish = (
            ma5 is not None
            and ma10 is not None
            and ma20 is not None
            and ma60 is not None
            and ma5 > ma10 > ma20 > ma60
        )
        bearish = (
            ma5 is not None
            and ma10 is not None
            and ma20 is not None
            and ma60 is not None
            and ma5 < ma10 < ma20 < ma60
        )

        if above_count >= 3 and bullish:
            return "上升趋势", "强势"
        if above_count >= 3:
            return "上升趋势", "中性"
        if below_count >= 3 and bearish:
            return "下降趋势", "弱势"
        if below_count >= 3:
            return "下降趋势", "中性"
        return "震荡", "中性"


_market_state_checker: MarketStateChecker | None = None


def get_market_state_checker() -> MarketStateChecker:
    global _market_state_checker
    if _market_state_checker is None:
        _market_state_checker = MarketStateChecker()
    return _market_state_checker
