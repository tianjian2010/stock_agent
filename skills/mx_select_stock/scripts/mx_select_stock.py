#!/usr/bin/env python3
"""
mx_select_stock - 妙想智能选股
用法: python mx_select_stock.py "选股条件" [--page 1] [--size 20] [--save]
"""

import sys, os, csv, argparse

APIKEY = os.environ.get("MX_API_KEY", os.environ.get("MX_APIKEY", ""))
ENDPOINT = os.environ.get(
    "MX_SELECT_URL",
    "https://mkapi2.dfcfs.com/finskillshub/api/claw/stock-screen",
)

COL_MAP = {
    "SERIAL": "序号", "SECURITY_CODE": "股票代码",
    "SECURITY_SHORT_NAME": "股票简称", "MARKET_SHORT_NAME": "市场",
    "NEWEST_PRICE": "最新价(元)", "CHG": "涨跌幅(%)", "PCHG": "涨跌额(元)",
    "TURNOVERRATE": "换手率(%)", "PE": "市盈率(动)", "PB": "市净率",
    "VOLUME_RATIO": "量比", "MARKET_CAPITAL": "总市值(元)",
    "FLOAT_MARKET_CAPITAL": "流通市值(元)", "HIGH_PRICE": "最高价(元)",
    "LOW_PRICE": "最低价(元)", "OPEN_PRICE": "开盘价(元)",
    "PRE_CLOSE": "昨收价(元)", "CLOSE_PRICE": "收盘价(元)",
    "AMOUNT": "成交额(元)", "VOLUME": "成交量(股)",
    "AMPLITUDE": "振幅(%)", "PS": "市销率",
}


def select_stock(keyword: str, page_no: int = 1, page_size: int = 20) -> dict:
    if not APIKEY:
        raise RuntimeError("Missing MX_API_KEY environment variable")
    import requests
    resp = requests.post(
        ENDPOINT,
        headers={"Content-Type": "application/json", "apikey": APIKEY},
        json={"keyword": keyword, "pageNo": page_no, "pageSize": page_size},
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()


def parse_partial_results(partial: str, columns: list) -> list:
    """解析 partialResults 管道符表格格式"""
    lines = partial.strip().split("|")
    if len(lines) < 3:
        return []
    # 第一行是表头（弃用，用columns映射）
    # 第二行是分隔符
    # 第三行起是数据
    data_lines = [l for l in lines if l.strip() and "---" not in l]
    if len(data_lines) < 2:
        return []

    headers = data_lines[0].split("|")[1:-1]  # 去掉首尾空
    rows = []
    for line in data_lines[2:]:
        cells = line.split("|")[1:-1]
        if len(cells) == len(headers):
            rows.append(cells)
    return rows


def format_markdown(rows: list, columns: list, col_map: dict) -> str:
    """Markdown 表格"""
    # 用 columns 里的 key 和 title 构建表头
    keys = [c.get("key", "") for c in columns]
    units = [c.get("unit", "") for c in columns]
    titles = [c.get("title", k) for c, k in zip(columns, keys)]
    titles = [f"{t} ({u})" if u else t for t, u in zip(titles, units)]

    header_disp = ["序号"] + titles
    keys_all = ["SERIAL"] + keys

    lines = ["| " + " | ".join(header_disp) + " |"]
    lines.append("|" + "|".join([" --- " for _ in header_disp]) + "|")

    for i, row_dict in enumerate(rows, 1):
        cells = [str(i)]
        for k in keys_all[1:]:
            v = str(row_dict.get(k, ""))
            try:
                fv = float(v)
                if abs(fv) > 10000:
                    v = f"{fv/1e8:.2f}亿" if fv > 0 else f"{fv:.2f}"
                elif "." in v:
                    v = f"{fv:.2f}"
            except:
                pass
            cells.append(v)
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def format_plain(rows: list, columns: list) -> str:
    """简洁文本格式（飞书友好）"""
    keys = [c.get("key", "SERIAL") for c in columns]
    out = []
    for row in rows:
        serial = row.get("SERIAL", "")
        code = row.get("SECURITY_CODE", "")
        name = row.get("SECURITY_SHORT_NAME", "")
        price = row.get("NEWEST_PRICE", "-")
        chg_raw = row.get("CHG", "0")
        try:
            chg_str = f"{float(chg_raw):+.2f}%"
        except:
            chg_str = str(chg_raw)
        market = row.get("MARKET_SHORT_NAME", "")
        mkt_map = {"SH": "沪", "SZ": "深", "HK": "港", "US": "美"}
        mkt_disp = mkt_map.get(market, market)
        out.append(f"  {serial:>3}. {code} {name}({mkt_disp}) 现价:{price} {chg_str}")
    return "\n".join(out)


def save_csv(rows: list, columns: list, keyword: str) -> str:
    os.makedirs("/workspace/mx_select_results", exist_ok=True)
    safe = "".join(c if c.isalnum() else "_" for c in keyword)[:40]
    path = f"/workspace/mx_select_results/{safe}.csv"
    keys = [c.get("key", "") for c in columns]
    headers = [COL_MAP.get(k, c.get("title", k)) for c, k in zip(columns, keys)]

    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["序号"] + headers)
        for i, row in enumerate(rows, 1):
            w.writerow([i] + [row.get(k, "") for k in keys])
    return path


def build_report(data: dict, keyword: str, page_no: int, page_size: int) -> str:
    inner = data.get("data", {}).get("data", {})

    # 优先从 partialResults 解析（管道符格式）
    partial = inner.get("partialResults", "")
    columns = inner.get("result", {}).get("columns", [])
    data_list = inner.get("result", {}).get("dataList", [])

    # 从 columns 提取 key→中文映射
    col_map = {c.get("key", ""): c.get("title", "") for c in columns}

    # 解析行数据
    rows = []
    if data_list:
        rows = data_list
    elif partial:
        raw_rows = parse_partial_results(partial, columns)
        # partial的列顺序: 序号|代码|名称|市场|最新价|涨跌幅|...
        # 建立索引映射
        partial_headers = [
            "SERIAL","SECURITY_CODE","SECURITY_SHORT_NAME","MARKET_SHORT_NAME",
            "NEWEST_PRICE","CHG","MARKET_TYPE","SECURITY_TYPE","PCHG",
            "HIGH_PRICE","LOW_PRICE","TURNOVERRATE","VOLUME_RATIO",
            "VOLUME","AMOUNT","PE","PB","MARKET_CAPITAL","FLOAT_MARKET_CAPITAL"
        ]
        for cells in raw_rows:
            row = {}
            for idx, val in enumerate(cells):
                if idx < len(partial_headers):
                    row[partial_headers[idx]] = val.strip()
            if row:
                rows.append(row)

    total = inner.get("result", {}).get("total", 0)
    cond_list = inner.get("responseConditionList", [])
    parser_text = inner.get("parserText", "")
    status = inner.get("result", {}).get("resultType", 0)

    lines = [
        f"🔍 **选股结果：{keyword}**",
        f"{'━'*40}",
        f"📊 共筛选出 **{total}** 只股票（第{page_no}页，每页{min(page_size, len(rows))}条）",
        "",
    ]

    if cond_list:
        lines.append("📋 **筛选条件：**")
        seen = set()
        for c in cond_list:
            desc = c.get("describe", "").strip("[]")
            cnt = c.get("stockCount", 0)
            if desc and desc not in seen:
                lines.append(f"  • {desc} → {cnt}只")
                seen.add(desc)
        lines.append("")

    if not rows:
        lines.append("⚠️ 未找到符合条件的股票，请尝试更换选股条件。")
        lines.append(f"\n原始返回: {data.get('message','无')}")
        return "\n".join(lines)

    lines.append("📈 **结果预览（部分）：**")
    lines.append("```")
    lines.append(format_plain(rows[:20], columns))
    lines.append("```\n")

    if len(rows) <= 30:
        lines.append("📋 **完整数据表：**")
        lines.append(format_markdown(rows, columns, col_map))

    return "\n".join(lines)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="妙想智能选股")
    p.add_argument("keyword", help="选股条件")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--size", type=int, default=20)
    p.add_argument("--save", action="store_true")
    args = p.parse_args()

    try:
        data = select_stock(args.keyword, args.page, min(args.size, 50))
        report = build_report(data, args.keyword, args.page, args.size)
        print(report)

        inner = data.get("data", {}).get("data", {})
        partial = inner.get("partialResults", "")
        columns = inner.get("result", {}).get("columns", [])
        rows = []
        if inner.get("result", {}).get("dataList"):
            rows = inner.get("result", {}).get("dataList", [])
        elif partial:
            raw_rows = parse_partial_results(partial, columns)
            partial_headers = [
                "SERIAL","SECURITY_CODE","SECURITY_SHORT_NAME","MARKET_SHORT_NAME",
                "NEWEST_PRICE","CHG","MARKET_TYPE","SECURITY_TYPE","PCHG",
                "HIGH_PRICE","LOW_PRICE","TURNOVERRATE","VOLUME_RATIO",
                "VOLUME","AMOUNT","PE","PB","MARKET_CAPITAL","FLOAT_MARKET_CAPITAL"
            ]
            for cells in raw_rows:
                row = {}
                for idx, val in enumerate(cells):
                    if idx < len(partial_headers):
                        row[partial_headers[idx]] = val.strip()
                if row:
                    rows.append(row)

        if args.save and rows:
            path = save_csv(rows, columns, args.keyword)
            print(f"\n[CSV已保存] {path}")

    except Exception as e:
        print(f"❌ 选股失败: {e}", file=sys.stderr)
        sys.exit(1)
