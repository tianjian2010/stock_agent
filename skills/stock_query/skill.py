"""Stock Query Skill - External stock data query skill."""

import logging
from typing import Any

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


class StockQuerySkill:
    """Stock query skill for external stock data."""

    name = "stock_query"
    description = "Query external stock market data and real-time information"

    def __init__(self):
        self._enabled = True

    def is_enabled(self) -> bool:
        return self._enabled

    def query_stock_price(self, symbol: str) -> dict[str, Any]:
        """Query stock price data.

        Args:
            symbol: Stock symbol (e.g., AAPL, TSLA)

        Returns:
            Stock price data
        """
        # Placeholder for external stock API integration
        # Implement actual API calls here
        logger.info(f"Querying stock price for {symbol}")
        return {
            "symbol": symbol,
            "price": 0.0,
            "change": 0.0,
            "change_pct": 0.0,
            "volume": 0,
            "timestamp": "",
        }

    def query_stock_info(self, symbol: str) -> dict[str, Any]:
        """Query stock information.

        Args:
            symbol: Stock symbol

        Returns:
            Stock information
        """
        logger.info(f"Querying stock info for {symbol}")
        return {
            "symbol": symbol,
            "name": "",
            "sector": "",
            "industry": "",
            "market_cap": 0,
            "pe_ratio": 0.0,
        }

    def query_historical_data(
        self,
        symbol: str,
        period: str = "1mo",
    ) -> dict[str, Any]:
        """Query historical stock data.

        Args:
            symbol: Stock symbol
            period: Time period (1d, 1mo, 3mo, 1y, etc.)

        Returns:
            Historical data
        """
        logger.info(f"Querying historical data for {symbol} period={period}")
        return {
            "symbol": symbol,
            "period": period,
            "data": [],
        }


def create_stock_query_tools() -> list[BaseTool]:
    """Create stock query tools."""
    from langchain_core.tools import tool

    skill = StockQuerySkill()

    @tool
    def query_stock_price(symbol: str) -> dict[str, Any]:
        """Query real-time stock price data.

        Args:
            symbol: Stock symbol (e.g., AAPL, TSLA, MSFT)

        Returns:
            Stock price data including current price, change, volume
        """
        return skill.query_stock_price(symbol)

    @tool
    def query_stock_info(symbol: str) -> dict[str, Any]:
        """Query stock basic information.

        Args:
            symbol: Stock symbol

        Returns:
            Stock info including name, sector, market cap
        """
        return skill.query_stock_info(symbol)

    @tool
    def query_historical_data(symbol: str, period: str = "1mo") -> dict[str, Any]:
        """Query historical stock data for charting.

        Args:
            symbol: Stock symbol
            period: Time period (1d, 1mo, 3mo, 6mo, 1y, 2y, 5y)

        Returns:
            Historical price data for charting
        """
        return skill.query_historical_data(symbol, period)

    return [query_stock_price, query_stock_info, query_historical_data]


# Global skill instance
_stock_skill: StockQuerySkill | None = None


def get_stock_query_skill() -> StockQuerySkill:
    """Get the stock query skill instance."""
    global _stock_skill
    if _stock_skill is None:
        _stock_skill = StockQuerySkill()
    return _stock_skill