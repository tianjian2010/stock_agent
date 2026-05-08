---
name: mx_search
description: 妙想资讯搜索（金融场景）。当用户询问股票、板块、宏观经济、政策、公告、研报等金融资讯时使用本技能。通过东方财富妙想API搜索权威金融信息，返回结构化搜索结果。比普通网页搜索更精准，专为金融场景设计，避免过时或非权威信息。
---

# 妙想资讯搜索 (mx_search)

基于东方财富妙想搜索的金融资讯检索技能，获取权威、及时的 A股/港股/美股资讯。

## 环境准备

API Key 已配置（存于 `MX_APIKEY`），直接使用脚本即可。

## 使用方式

### Python 脚本（推荐）

```bash
python3 /workspace/skills/mx_search/scripts/mx_search.py "关键词"
```

**选项：**
- `--save` 将结果 JSON 保存到 `/workspace/mx_search_results/`

**示例查询：**
```bash
python3 /workspace/skills/mx_search/scripts/mx_search.py "昆仑万维 最新公告"
python3 /workspace/skills/mx_search/scripts/mx_search.py "AI算力 政策"
python3 /workspace/skills/mx_search/scripts/mx_search.py "美联储加息 A股影响"
```

### Shell 脚本（备用）

```bash
bash /workspace/skills/mx_search/scripts/mx_search.sh "关键词"
```

## 适用场景

| 类型 | 示例问句 |
|------|---------|
| 个股资讯 | "格力电器最新研报"、"贵州茅台机构观点" |
| 板块/主题 | "商业航天板块近期新闻"、"新能源政策解读" |
| 宏观/风险 | "美联储加息对A股影响"、"人民币贬值受益股" |
| 公告/事件 | "某股票重组公告"、"年报业绩超预期" |
| 综合解读 | "今日大盘异动原因"、"北向资金流向" |

## 返回字段说明

| 字段 | 含义 |
|------|------|
| `title` | 资讯标题 |
| `secuList[].secuCode` | 证券代码 |
| `secuList[].secuName` | 证券名称 |
| `secuList[].secuType` | 证券类型 |
| `trunk` | 核心正文 / 结构化数据 |
| `source` | 来源媒体 |
| `publishTime` | 发布时间 |

## 输出格式

脚本执行后会输出格式化文本，每条资讯包含：
- 📌 关联股票代码+名称
- 📍 来源 + 发布时间
- 💬 正文摘要（前300字）

## 注意事项

- 每次搜索独立调用，不要将多个关键词用"+"拼接在同一字符串
- 如需同时搜多个主题，请分多次调用
- 搜索结果默认不保存本地；加 `--save` 可保存 JSON 原始结果
