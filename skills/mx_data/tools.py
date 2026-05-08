"""MX Stock Query Tools - LangChain tools for A股 stock skills."""

from langchain_core.tools import tool

from skills.mx_data import (
    get_mx_data_skill,
    get_mx_search_skill,
    get_mx_select_skill,
)


@tool
def query_a_stock_price(stock_name: str) -> str:
    """Query A股实时行情数据。

    Args:
        stock_name: 股票名称或代码，例如 "东方财富"、"贵州茅台"、"600859"

    Returns:
        格式化后的行情数据
    """
    skill = get_mx_data_skill()
    result = skill.query(stock_name + "最新价")
    return skill.format_result(result)


@tool
def query_a_stock_finance(stock_name: str) -> str:
    """Query A股财务数据。

    Args:
        stock_name: 股票名称或代码

    Returns:
        格式化后的财务数据
    """
    skill = get_mx_data_skill()
    result = skill.query(stock_name + "财务指标")
    return skill.format_result(result)


@tool
def query_a_stock_money_flow(stock_name: str) -> str:
    """Query A股主力资金流向。

    Args:
        stock_name: 股票名称或代码

    Returns:
        格式化后的资金流向
    """
    skill = get_mx_data_skill()
    result = skill.query(stock_name + "主力资金流向")
    return skill.format_result(result)


@tool
def query_financial_news(keyword: str) -> str:
    """搜索金融资讯、新闻、研报。

    Args:
        keyword: 搜索关键词，例如 "AI概念股"、"新能源政策"

    Returns:
        格式化后的搜索结果
    """
    skill = get_mx_search_skill()
    result = skill.search(keyword)
    return skill.format_result(result)


@tool
def select_stocks(condition: str, page: int = 1, size: int = 20) -> str:
    """按条件筛选股票。

    Args:
        condition: 选股条件，例如 "市盈率低于20的医药股"、"今日涨幅超过3%的AI概念股"
        page: 页码，默认1
        size: 每页数量，默认20

    Returns:
        格式化后的选股结果
    """
    skill = get_mx_select_skill()
    result = skill.select(condition, page, size)
    return skill.format_result(result)


# 导出所有tools
STOCK_QUERY_TOOLS = [
    query_a_stock_price,
    query_a_stock_finance,
    query_a_stock_money_flow,
    query_financial_news,
    select_stocks,
]