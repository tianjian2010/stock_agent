#!/bin/bash
# mx_search - 妙想资讯搜索
# 用法: ./mx_search.sh "搜索关键词"
# 输出: JSON 格式搜索结果

QUERY="$1"
APIKEY="${MX_API_KEY:-${MX_APIKEY:-}}"

if [ -z "$QUERY" ]; then
  echo "错误: 请提供搜索关键词"
  echo "用法: $0 \"关键词\""
  exit 1
fi

if [ -z "$APIKEY" ]; then
  echo "错误: 缺少 MX_API_KEY 环境变量"
  exit 1
fi

RESPONSE=$(curl -s -X POST 'https://mkapi2.dfcfs.com/finskillshub/api/claw/news-search' \
  -H "Content-Type: application/json" \
  -H "apikey: $APIKEY" \
  -d "{\"query\":\"$QUERY\"}")

echo "$RESPONSE"
