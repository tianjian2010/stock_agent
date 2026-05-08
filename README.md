# Stock Agent

面向 A 股研究场景的对话式 Agent 工作台。当前仓库只保留 `React + Vite` 前端和 `FastAPI` 后端两条主链路，旧 `Streamlit` 入口已移除。

## 当前架构

```text
app/
  api/main.py              FastAPI 入口
  api/chat.py              聊天、历史会话、统计与流式接口
frontend/
  src/                     React 前端主应用
agents/
  stock_agent/agent.py     主 Agent 编排
services/
  db.py                    PostgreSQL 会话持久化
  memory.py                会话记忆与摘要
  document_retriever.py    文档检索
  vector_store.py          向量存储
skills/
  mx_data/                 行情、资讯、选股工具封装
stock_docs/                本地投研资料
tests/                     关键路径测试
```

## 默认启动方式

1. 安装 Python 依赖

```bash
pip install -r requirements.txt
```

2. 安装前端依赖

```bash
cd frontend
npm install
cd ..
```

3. 配置环境变量

复制 `.env.example` 为 `.env`，至少补齐：

```bash
DATABASE_URL=
MINIMAX_API_KEY=
MX_API_KEY=
FRONTEND_ORIGINS=http://localhost:5173,http://localhost:3000
```

前端默认读取：

```bash
frontend/.env
VITE_API_BASE_URL=http://localhost:8000
```

4. 启动后端

```bash
python -m app.api.main
```

默认地址：`http://localhost:8000`

5. 启动前端

```bash
cd frontend
npm run dev
```

默认地址：`http://localhost:5173`

## 可选：使用一键启动脚本

仓库根目录提供了两个 PowerShell 脚本：

```bash
scripts/start_api.ps1
scripts/start_frontend.ps1
```

分别用于启动 FastAPI 和 React 前端。

## 当前前端范围

- 首页引导
- 聊天主界面
- 会话历史、新建、删除、切换
- 引用 / 工具 / 轨迹 / 恢复面板
- 流式状态反馈
- 移动端基础可用性

## 测试与构建

后端测试：

```bash
python -m unittest discover -s tests -v
```

前端构建：

```bash
cd frontend
npm run build
```
