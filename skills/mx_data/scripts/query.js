#!/usr/bin/env node

const API_URL = process.env.MX_DATA_URL || 'https://mkapi2.dfcfs.com/finskillshub/api/claw/query';
const API_KEY = process.env.MX_API_KEY || process.env.MX_APIKEY || '';

async function query(queryStr) {
  if (!API_KEY) {
    throw new Error('Missing MX_API_KEY environment variable');
  }
  const response = await fetch(API_URL, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'apikey': API_KEY
    },
    body: JSON.stringify({ toolQuery: queryStr })
  });
  
  if (!response.ok) {
    throw new Error(`API请求失败: ${response.status}`);
  }
  
  const data = await response.json();
  return data;
}

// 主程序
const queryStr = process.argv[2] || '东方财富最新价';

console.log(`正在查询: ${queryStr}\n`);

try {
  const result = await query(queryStr);
  console.log(JSON.stringify(result, null, 2));
} catch (error) {
  console.error('查询失败:', error.message);
  process.exit(1);
}
