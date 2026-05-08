#!/bin/bash
# mx_select_stock - 妙想智能选股
# 用法: ./mx_select_stock.sh "选股条件" [pageNo] [pageSize]
# 示例: ./mx_select_stock.sh "今日涨幅2%的股票" 1 20

KEYWORD="${1:-}"
PAGE_NO="${2:-1}"
PAGE_SIZE="${3:-20}"
APIKEY="${MX_API_KEY:-${MX_APIKEY:-}}"

if [ -z "$KEYWORD" ]; then
  echo "错误: 请提供选股条件关键词"
  echo "用法: $0 \"选股条件\" [pageNo] [pageSize]"
  exit 1
fi

if [ -z "$APIKEY" ]; then
  echo "错误: 缺少 MX_API_KEY 环境变量"
  exit 1
fi

RESPONSE=$(curl -s -X POST 'https://mkapi2.dfcfs.com/finskillshub/api/claw/stock-screen' \
  -H "Content-Type: application/json" \
  -H "apikey: $APIKEY" \
  -d "{\"keyword\":\"$KEYWORD\",\"pageNo\":$PAGE_NO,\"pageSize\":$PAGE_SIZE}")

echo "$RESPONSE"
