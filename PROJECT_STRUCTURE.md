# Stock Agent 项目结构

## 当前定位

当前仓库已经完成前后端分离切换，主入口如下：

- 默认产品入口：`React + Vite`
- 默认服务入口：`FastAPI`

旧 `Streamlit` 入口已移除，仓库当前只保留 API 和前端工作台两条主链路。

## 当前目录结构

```text
stock_agent/
├─ app/
│  └─ api/
│     ├─ main.py                 FastAPI 入口
│     └─ chat.py                 聊天、历史、统计、流式接口
├─ frontend/
│  ├─ src/
│  │  ├─ app/
│  │  ├─ features/
│  │  │  ├─ chat/
│  │  │  ├─ citations/
│  │  │  ├─ diagnostics/
│  │  │  └─ history/
│  │  ├─ hooks/
│  │  ├─ lib/
│  │  ├─ pages/
│  │  │  ├─ chat/
│  │  │  └─ home/
│  │  ├─ styles/
│  │  └─ types/
│  ├─ package.json
│  └─ vite.config.ts
├─ agents/
│  └─ stock_agent/
│     ├─ agent.py                主 Agent 编排
│     ├─ runtime.py              计划、任务、批次、恢复策略
│     └─ subagents.py            子 Agent 注册与执行
├─ services/
│  ├─ db.py                      PostgreSQL 持久化
│  ├─ memory.py                  多轮记忆与摘要
│  ├─ document_retriever.py      文档检索
│  ├─ doc_loader.py              文档加载
│  ├─ vector_store.py            向量存储
│  ├─ transcript_store.py        转写文件管理
│  └─ llm.py                     模型接入
├─ skills/
│  └─ mx_data/                   行情、资讯、选股工具封装
├─ stock_docs/                   本地投研资料
├─ scripts/
│  ├─ start_api.ps1              启动 FastAPI
│  └─ start_frontend.ps1         启动 React 前端
├─ tests/
├─ README.md
├─ FRONTEND_REBUILD_PLAN.md
└─ requirements.txt
```

## 主入口说明

### 前端主入口

- 路径：`frontend/`
- 技术栈：React 19 + TypeScript + Vite
- 作用：首页、聊天页、历史会话、引用/工具/轨迹/恢复面板

### 后端主入口

- 路径：`app/api/main.py`
- 技术栈：FastAPI
- 作用：对外提供聊天、历史会话、统计、流式接口

## 启动方式

1. 启动 FastAPI

```bash
python -m app.api.main
```

或：

```bash
scripts/start_api.ps1
```

2. 启动 React 前端

```bash
cd frontend
npm run dev
```

或：

```bash
scripts/start_frontend.ps1
```

## 当前已完成的切换

- 新首页与聊天页已成为默认交互入口
- 会话历史、新建、删除、切换已迁移到前端
- 引用、工具结果、执行轨迹、恢复信息已迁移到前端诊断面板
- 流式输出和状态反馈已迁移到前端
- 移动端基础可用性已补齐
- `Streamlit` 相关源码已移除
