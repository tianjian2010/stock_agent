"""A-share stock data skills."""

import json
import logging
from typing import Any

import requests

from app.config import MX_API_KEY, MX_DATA_KLINE_URL, MX_DATA_URL, MX_SEARCH_URL, MX_SELECT_URL

logger = logging.getLogger(__name__)


class _BaseMXSkill:
    timeout = 30

    @staticmethod
    def _require_api_key() -> str:
        if not MX_API_KEY:
            raise ValueError(
                "Missing MX_API_KEY. Please set it in the environment before using market data tools."
            )
        return MX_API_KEY

    def _post(self, url: str, payload: dict[str, Any]) -> dict[str, Any]:
        try:
            response = requests.post(
                url,
                headers={
                    "Content-Type": "application/json",
                    "apikey": self._require_api_key(),
                },
                json=payload,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return response.json()
        except Exception as exc:
            logger.exception("MX request failed: %s", exc)
            return {"error": str(exc)}


class MXDataSkill(_BaseMXSkill):
    """Market data skill."""

    name = "mx_data"
    description = "查询 A 股实时行情、财务数据和资金流向"

    def query(self, query_str: str) -> dict[str, Any]:
        return self._post(MX_DATA_URL, {"toolQuery": query_str})

    def query_kline(
        self,
        stock_code: str,
        *,
        period: str = "day",
        count: int = 120,
        adjust: str = "qfq",
    ) -> dict[str, Any]:
        payload = {
            "stockCode": stock_code,
            "period": period,
            "count": count,
            "adjust": adjust,
        }
        return self._post(MX_DATA_KLINE_URL, payload)

    def format_result(self, data: dict[str, Any]) -> str:
        if error := data.get("error"):
            return f"行情查询失败: {error}"

        inner = data.get("data", {})
        if not inner:
            return json.dumps(data, ensure_ascii=False, indent=2)

        search_data = inner.get("data", {}).get("searchDataResultDTO", {})
        tables = search_data.get("dataTableDTOList", [])
        if tables:
            lines = ["行情数据："]
            for table_data in tables[:5]:
                code = table_data.get("code", "")
                name = (table_data.get("entityName", "") or code).replace("\ufffd", "").strip()
                table = table_data.get("table", {})
                latest_values = table.get("325898", [])
                if name and latest_values:
                    lines.append(f"- {code} {name}: {latest_values[0]}")
            if len(lines) > 1:
                return "\n".join(lines)

        diff_rows = inner.get("data", {}).get("diff", [])
        if diff_rows:
            lines = ["行情数据："]
            for row in diff_rows[:10]:
                code = row.get("code", "")
                name = row.get("name", "")
                price = row.get("price", row.get("f2", "-"))
                change = row.get("change", row.get("f4", "0"))
                try:
                    change_display = f"{float(change):+.2f}%"
                except (TypeError, ValueError):
                    change_display = str(change)
                # Extract additional technical fields when available
                parts = [f"- {code} {name}: {price} ({change_display})"]
                day_high = row.get("f15", "")
                day_low = row.get("f16", "")
                if day_high and day_low:
                    parts.append(f" 高{day_high}/低{day_low}")
                open_price = row.get("f17", "")
                prev_close = row.get("f18", "")
                if open_price:
                    parts.append(f" 开{open_price}")
                if prev_close:
                    parts.append(f" 昨收{prev_close}")
                lines.append("".join(parts))
            return "\n".join(lines)

        return json.dumps(data, ensure_ascii=False, indent=2)


class MXSearchSkill(_BaseMXSkill):
    """Financial news search skill."""

    name = "mx_search"
    description = "搜索金融资讯、新闻和研报"

    def search(self, query: str) -> dict[str, Any]:
        return self._post(MX_SEARCH_URL, {"query": query})

    def format_result(self, data: dict[str, Any]) -> str:
        if error := data.get("error"):
            return f"资讯搜索失败: {error}"

        news_list = data.get("data", {}).get("newsList", [])
        if not news_list:
            return "未找到相关新闻。"

        lines = [f"找到 {len(news_list)} 条相关资讯："]
        for index, item in enumerate(news_list[:10], start=1):
            title = item.get("title", "无标题")
            source = item.get("source", "")
            publish_time = item.get("publishTime", "")
            summary = item.get("trunk", "")[:200]
            lines.append(f"{index}. {title}")
            if source:
                lines.append(f"   来源: {source}")
            if publish_time:
                lines.append(f"   时间: {publish_time}")
            if summary:
                lines.append(f"   摘要: {summary}...")
        return "\n".join(lines)


class MXSelectStockSkill(_BaseMXSkill):
    """Stock screening skill."""

    name = "mx_select_stock"
    description = "按条件筛选股票"

    def select(
        self,
        keyword: str,
        page_no: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        return self._post(
            MX_SELECT_URL,
            {"keyword": keyword, "pageNo": page_no, "pageSize": page_size},
        )

    def format_result(self, data: dict[str, Any]) -> str:
        if error := data.get("error"):
            return f"选股失败: {error}"

        result = data.get("data", {}).get("data", {}).get("result", {})
        total = result.get("total", 0)
        data_list = result.get("dataList", [])
        if not data_list:
            return "未找到符合条件的股票。"

        market_map = {"SH": "沪", "SZ": "深", "HK": "港", "US": "美"}
        lines = [f"共筛选出 {total} 只股票："]
        for index, row in enumerate(data_list[:20], start=1):
            code = row.get("SECURITY_CODE", "")
            name = row.get("SECURITY_SHORT_NAME", "")
            market = market_map.get(row.get("MARKET_SHORT_NAME", ""), row.get("MARKET_SHORT_NAME", ""))
            price = row.get("NEWEST_PRICE", "-")
            change = row.get("CHG", "0")
            try:
                change_display = f"{float(change):+.2f}%"
            except (TypeError, ValueError):
                change_display = str(change)
            lines.append(f"{index}. {code} {name}({market}): {price} ({change_display})")
        return "\n".join(lines)


_mx_data: MXDataSkill | None = None
_mx_search: MXSearchSkill | None = None
_mx_select: MXSelectStockSkill | None = None


def get_mx_data_skill() -> MXDataSkill:
    global _mx_data
    if _mx_data is None:
        _mx_data = MXDataSkill()
    return _mx_data


def get_mx_search_skill() -> MXSearchSkill:
    global _mx_search
    if _mx_search is None:
        _mx_search = MXSearchSkill()
    return _mx_search


def get_mx_select_skill() -> MXSelectStockSkill:
    global _mx_select
    if _mx_select is None:
        _mx_select = MXSelectStockSkill()
    return _mx_select
