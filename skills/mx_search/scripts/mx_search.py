#!/usr/bin/env python3
"""
mx_search - 妙想资讯搜索
用法: python mx_search.py "搜索关键词" [--save]

依赖: pip install requests
"""

import sys
import json
import os
import argparse

APIKEY = os.environ.get("MX_API_KEY", os.environ.get("MX_APIKEY", ""))
ENDPOINT = os.environ.get(
    "MX_SEARCH_URL",
    "https://mkapi2.dfcfs.com/finskillshub/api/claw/news-search",
)


def search(query: str, save: bool = False) -> dict:
    if not APIKEY:
        raise RuntimeError("Missing MX_API_KEY environment variable")
    import requests
    resp = requests.post(
        ENDPOINT,
        headers={"Content-Type": "application/json", "apikey": APIKEY},
        json={"query": query},
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if save:
        safe_name = query.replace("/", "_").replace(" ", "_")[:40]
        path = f"/workspace/mx_search_results/{safe_name}.json"
        os.makedirs("/workspace/mx_search_results", exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"[已保存] {path}", file=sys.stderr)

    return data


def format_result(data: dict) -> str:
    """将妙想API返回的JSON格式化为易读的文本"""
    news_list = data.get("data", {}).get("newsList", []) if isinstance(data, dict) else []

    if not news_list:
        # 兼容某些接口直接把列表放顶层的响应
        if isinstance(data, list):
            news_list = data
        else:
            return f"⚠️ 未找到相关资讯。原始返回：\n{json.dumps(data, ensure_ascii=False, indent=2)}"

    lines = [f"📰 搜索到 {len(news_list)} 条相关资讯：\n"]
    for i, item in enumerate(news_list, 1):
        title = item.get("title", "无标题")
        secu_list = item.get("secuList", [])
        tickers = " | ".join([f"{s.get('secuCode','')} {s.get('secuName','')}" for s in secuList]) if (secuList := item.get("secuList")) else ""
        trunk = item.get("trunk", "（无正文）")
        source = item.get("source", item.get("media", ""))
        publish_time = item.get("publishTime", item.get("publish_time", ""))

        lines.append(f"{'─'*40}")
        lines.append(f"{i}. 【{title}】")
        if tickers:
            lines.append(f"   📌 {tickers}")
        if source:
            lines.append(f"   📍 来源: {source}")
        if publish_time:
            lines.append(f"   🕐 时间: {publish_time}")
        lines.append(f"   💬 {trunk[:300]}{'...' if len(trunk) > 300 else ''}")
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="妙想资讯搜索")
    parser.add_argument("query", help="搜索关键词")
    parser.add_argument("--save", action="store_true", help="保存结果到工作目录")
    args = parser.parse_args()

    try:
        data = search(args.query, save=args.save)
        print(format_result(data))
    except Exception as e:
        print(f"❌ 搜索失败: {e}", file=sys.stderr)
        sys.exit(1)
