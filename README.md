# Stock Agent

面向 A 股研究场景的对话式 Agent 工作台。当前仓库只保留 `React + Vite` 前端和 `FastAPI` 后端两条主链路，旧 `Streamlit` 入口已移除。

## 当前架构

```text
app/
  api/main.py              FastAPI 入口
  api/chat.py              聊天、历史会话、统计与流式接口
  config.py                 全局配置（环境变量、模型、参数）
frontend/
  src/                     React 前端主应用
agents/
  stock_agent/agent.py     主 Agent 编排（规划、调度、合成）
  stock_agent/runtime.py   运行时原语（意图检测、工具规划、任务图）
  stock_agent/subagents.py 子 Agent 执行器（文档、行情、新闻、选股、趋势）
  stock_agent/time_router.py 时间意图路由（日摘要 / 时间窗口统计 / 行情研判）
services/
  db.py                    PostgreSQL 会话持久化
  memory.py                会话记忆与摘要
  document_retriever.py    文档检索（向量 + 词法双路）
  doc_fact_index.py        文档事实索引（股票提及抽取、时间窗口聚合）
  doc_loader.py            文档加载器（txt/docx/pdf/xlsx）
  vector_store.py          向量存储（ChromaDB）
  market_state_checker.py  行情研判（突破检测、趋势分析、均线计算）
  llm.py                   LLM 服务封装（MiniMax / OpenAI 兼容）
skills/
  mx_data/                 妙想金融数据（实时行情、财务、资金流向）
  mx_search/               妙想资讯搜索
  mx_select_stock/         妙想智能选股
stock_docs/                本地投研资料（标准化文件名：{topic}__{date}__v{version}）
tests/                     关键路径测试（64 个用例）
scripts/
  preprocess_docs.py       文档预处理（文件名标准化、去重、版本管理）
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
日志默认同时输出到终端和 `data/logs/stock_agent.log`，可通过 `.env` 里的 `LOG_*` 变量调整。

5. 启动前端

```bash
cd frontend
npm run dev
```

默认地址：`http://localhost:5173`

## MiniMax 直连自检

如果怀疑应用内的 MiniMax LLM 连通性有问题，可以先跳过应用启动，直接做一次最小请求验证：

```bash
python scripts/check_minimax_llm.py
```

它会读取项目根目录 `.env` 里的 `MINIMAX_API_KEY`、`MINIMAX_BASE_URL`、`MINIMAX_MODEL`，输出一段 JSON，并将结果区分为 `ok`、`invalid_api_key`、`connection_error`、`timeout`、`bad_base_url` 等类别。

也支持临时覆盖参数，例如：

```bash
python scripts/check_minimax_llm.py --base-url https://api.minimaxi.com/v1 --model MiniMax-M2.7 --timeout 8
```

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
