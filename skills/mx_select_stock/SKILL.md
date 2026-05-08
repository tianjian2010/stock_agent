---
name: mx_select_stock
description: 妙想智能选股（金融场景）。当用户需要按条件筛选股票、查询行业板块成分股、获取股票/板块推荐时使用本技能。通过东方财富妙想选股API，支持A股/港股/美股的行情指标、财务指标等条件筛选，返回结构化股票列表。比普通搜索更精准，专为选股设计，避免过时或非权威信息。
---

# 妙想智能选股 (mx_select_stock)

基于东方财富妙想智能选股 API，支持自然语言选股条件。

## 环境准备

API Key 已配置（存于 `MX_APIKEY`，与 mx_search 共用同一 Key）。

## 使用方式

### Python 脚本（推荐）

```bash
python3 /workspace/skills/mx_select_stock/scripts/mx_select_stock.py "选股条件" [--page N] [--size N] [--save]
```

**参数说明：**
- `keyword`（必填）：选股条件，支持自然语言
- `--page`：页码，默认 1
- `--size`：每页条数，默认 20，最大 50
- `--save`：保存 CSV 到 `/workspace/mx_select_results/`

**示例：**
```bash
python3 /workspace/skills/mx_select_stock/scripts/mx_select_stock.py "今日涨幅超过3%的AI概念股"
python3 /workspace/skills/mx_select_stock/scripts/mx_select_stock.py "市盈率低于20的医药股" --size 30 --save
python3 /workspace/skills/mx_select_stock/scripts/mx_select_stock.py "科创板半导体股票"
```

### Shell 脚本（备用）

```bash
bash /workspace/skills/mx_select_stock/scripts/mx_select_stock.sh "选股条件" [pageNo] [pageSize]
```

## 适用场景

| 类型 | 示例问句 |
|------|---------|
| 行情选股 | "今日涨幅2%的股票"、"换手率超过5%的股票" |
| 财务选股 | "市盈率低于20的股票"、"ROE超过15%的公司" |
| 板块选股 | "半导体行业股票"、"科创板AI概念股" |
| 综合条件 | "今日主力资金净流入超1亿的科技股" |
| 板块成分 | "中证500成分股"、"创业板权重股" |

## 返回字段说明

| 字段 | 含义 |
|------|------|
| `SECURITY_CODE` | 股票代码 |
| `SECURITY_SHORT_NAME` | 股票简称 |
| `MARKET_SHORT_NAME` | 市场（SH=沪/SZ=深） |
| `NEWEST_PRICE` | 最新价（元） |
| `CHG` | 涨跌幅（%） |
| `PCHG` | 涨跌额（元） |
| `TURNOVERRATE` | 换手率（%） |
| `PE` | 市盈率 |
| `PB` | 市净率 |
| `VOLUME_RATIO` | 量比 |

## 输出格式

执行后返回：
- 📋 筛选条件说明 + 匹配股数
- 📈 股票列表（简洁格式）
- 📊 Markdown 数据表格（≤30条时）
- 💾 原始 CSV（如加 `--save`）

## 注意事项

- 每次调用独立选股，支持 A股 / 港股 / 美股
- CSV 默认保存到 `/workspace/mx_select_results/`
- 如返回"未找到"，建议更换或简化选股条件
