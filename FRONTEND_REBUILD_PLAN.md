# Frontend 重构实施清单

## 1. 目标

把当前基于 `Streamlit` 的聊天界面，升级为一个真正的前后端分离 Web 应用：

- 交互体验接近 `ChatGPT / MiniMax` 的首页聊天产品
- 保留现有 Python `FastAPI + Agent` 能力，不重写核心业务
- 让 UI、状态管理、流式输出、历史会话、引用面板都可持续演进
- 为后续登录、分享、文件上传、工作台扩展预留空间

当前判断：

- 后端主干已经具备拆前端的基础
- `Streamlit` 主要问题在于 UI 表达力、状态组织、组件扩展性不足
- 最优路线是 `保留 FastAPI，新增 React 前端，逐步替换 Streamlit`

---

## 2. 推荐技术栈

### 2.1 最终建议

- 框架：`React 19 + TypeScript`
- 构建工具：`Vite`
- 路由：`React Router`
- 服务端数据管理：`TanStack Query`
- 样式方案：`Tailwind CSS`
- 图标：`Lucide React`
- 动效：`Motion`
- 文本渲染：`react-markdown`

### 2.2 为什么这样选

- `React` 生态最成熟，招聘、维护、组件资源都最稳
- `Vite` 对这种聊天工作台场景最轻、开发体验最好
- 当前项目后端已经是 `FastAPI`，不需要 `Next.js` 再承担服务端职责
- `TanStack Query` 很适合管理聊天请求、历史会话、重试、缓存失效
- `Tailwind CSS` 能快速做出高完成度页面，同时方便做设计系统

### 2.3 暂不建议

- `Next.js`
  - 不是不能用，而是对当前项目收益不够大
  - 你的核心不是 SSR、SEO、内容分发，而是聊天工作台
- `Vue / Nuxt`
  - 也能做，但当前 Python Agent 项目配 React 社区范式更通用
- 继续增强 `Streamlit`
  - 能修补，但长期体验和扩展性上限低

---

## 3. 重构原则

1. 后端先补 contract，再做前端页面
2. 新前端与旧 `Streamlit` 并行一段时间，避免一次性切换
3. 优先跑通聊天主链路，再补“引用 / 工具 / 轨迹”侧边能力
4. API 输出结构稳定后，前端组件按模块拆分
5. 第一版就按产品级结构搭，不做一次性 demo

---

## 4. 当前系统可复用部分

以下内容建议直接复用：

- [app/api/main.py](/c:/AI_tech/projects/stock_agent/app/api/main.py:1)
- [app/api/chat.py](/c:/AI_tech/projects/stock_agent/app/api/chat.py:1)
- `agents/stock_agent/*`
- `services/db.py`
- `services/document_retriever.py`
- `services/memory.py`

以下内容建议逐步淘汰为“调试入口”：

- [app/main.py](/c:/AI_tech/projects/stock_agent/app/main.py:1)
- [app/web/chat_page.py](/c:/AI_tech/projects/stock_agent/app/web/chat_page.py:1)

---

## 5. 目标目录结构

建议新增：

```text
stock_agent/
├─ app/
│  ├─ api/
│  └─ web/                       # 旧 Streamlit，过渡期保留
├─ frontend/
│  ├─ public/
│  ├─ src/
│  │  ├─ app/
│  │  │  ├─ router.tsx
│  │  │  ├─ providers.tsx
│  │  │  └─ main.tsx
│  │  ├─ pages/
│  │  │  ├─ home/
│  │  │  └─ chat/
│  │  ├─ features/
│  │  │  ├─ chat/
│  │  │  ├─ history/
│  │  │  ├─ citations/
│  │  │  ├─ tools/
│  │  │  └─ diagnostics/
│  │  ├─ components/
│  │  │  ├─ layout/
│  │  │  ├─ ui/
│  │  │  └─ markdown/
│  │  ├─ lib/
│  │  │  ├─ api/
│  │  │  ├─ utils/
│  │  │  └─ constants/
│  │  ├─ hooks/
│  │  ├─ styles/
│  │  ├─ types/
│  │  └─ assets/
│  ├─ package.json
│  ├─ tsconfig.json
│  ├─ vite.config.ts
│  └─ tailwind.config.ts
└─ FRONTEND_REBUILD_PLAN.md
```

---

## 6. 页面信息架构

### 6.1 首屏

目标不是直接显示一个朴素聊天框，而是做成产品首页：

- 品牌标题区
- 一句明确定位
- 预设问题卡片
- 输入框固定在视觉中心
- 最近会话入口

建议风格：

- 偏专业研究工作台，不要做成娱乐型 AI
- 关键词：`金融研究 / 深色中性 / 玻璃感弱化 / 信息密度克制 / 字体更锐利`

### 6.2 聊天页

三栏布局优先：

- 左栏：历史会话、新建、搜索、删除
- 中栏：消息流、欢迎态、输入区、流式输出
- 右栏：资料引用、工具结果、执行轨迹、恢复信息

移动端退化：

- 左右栏改为抽屉
- 中栏保留核心输入和消息流

---

## 7. 前端功能拆分

### 7.1 `history`

- 获取历史会话列表
- 新建会话
- 删除会话
- 打开指定会话
- 高亮当前会话

### 7.2 `chat`

- 发送问题
- 追加用户消息
- 追加助手消息
- 显示 loading 状态
- 支持流式输出
- 支持消息失败后的重试

### 7.3 `citations`

- 展示资料文件名
- 展示发布日期
- 按回答关联引用分组
- 预留“点击展开片段”能力

### 7.4 `tools`

- 展示工具调用结果
- 区分 `ok / recovered / degraded / failed`
- 折叠展示错误细节

### 7.5 `diagnostics`

- 展示 `plan`
- 展示 `trace`
- 展示 `recovery summary`
- 默认折叠，避免打断主阅读流

---

## 8. 后端 API 改造清单

当前 API 已经能支撑基础聊天，但还不够适合现代前端。

### 8.1 现有接口可保留

- `POST /api/chat`
- `GET /api/chat/history`
- `GET /api/chat/history/{thread_id}`
- `POST /api/chat/history`
- `DELETE /api/chat/history/{thread_id}`
- `GET /api/chat/stats`
- `GET /health`

### 8.2 需要补强的响应结构

当前 `POST /api/chat` 建议补充：

```json
{
  "thread_id": "uuid",
  "title": "创新药近期景气度",
  "answer": "string",
  "citations": [],
  "tool_results": [],
  "plan": {},
  "trace": [],
  "recovery": {},
  "created_at": "ISO_DATETIME"
}
```

说明：

- `title` 让前端首轮消息后能立即刷新会话标题
- `plan` 和 `trace` 现在 Streamlit 已经在用，API 应同步透出
- `created_at` 方便前端做 optimistic UI 与排序

### 8.3 历史消息接口统一结构

建议 `GET /api/chat/history/{thread_id}` 返回：

```json
{
  "thread_id": "uuid",
  "title": "string",
  "messages": [
    {
      "id": 1,
      "role": "user",
      "content": "string",
      "metadata": {},
      "created_at": "ISO_DATETIME"
    }
  ]
}
```

不要直接返回裸数组，方便后续扩展。

### 8.4 新增流式接口

建议新增：

- `POST /api/chat/stream`

返回建议采用 `SSE`，事件可分层：

```text
event: message_start
data: {"thread_id":"..."}

event: answer_delta
data: {"delta":"当前片段"}

event: tool_result
data: {...}

event: citations
data: {...}

event: trace
data: {...}

event: answer_done
data: {"answer":"完整答案"}

event: done
data: {"ok":true}
```

### 8.5 CORS 配置化

当前 [app/api/main.py](/c:/AI_tech/projects/stock_agent/app/api/main.py:1) 里只允许 `localhost:3000/3001`，建议改为环境变量：

- `FRONTEND_ORIGINS=http://localhost:5173,http://localhost:3000`

---

## 9. 前端数据模型

建议在 `frontend/src/types` 统一定义：

```ts
export type ChatRole = "user" | "assistant";

export interface Citation {
  filename: string;
  published_at?: string | null;
  snippet?: string | null;
}

export interface ToolResult {
  name: string;
  success?: boolean;
  recovered?: boolean;
  degraded?: boolean;
  reason?: string;
  error_message?: string;
}

export interface ChatMessage {
  id?: number;
  role: ChatRole;
  content: string;
  metadata?: {
    citations?: Citation[];
    tool_results?: ToolResult[];
    plan?: Record<string, unknown>;
    trace?: Record<string, unknown>[];
    recovery?: Record<string, unknown>;
  };
  created_at?: string;
}
```

重点：

- 前端所有展示都围绕 `ChatMessage` 做
- `metadata` 保持可扩展，不要把临时字段散落在多个组件里

---

## 10. UI 组件清单

第一批建议实现这些组件：

- `AppShell`
- `SidebarChatHistory`
- `ChatHeader`
- `WelcomeHero`
- `PromptComposer`
- `MessageList`
- `MessageBubble`
- `AssistantMarkdown`
- `TypingIndicator`
- `RightPanel`
- `CitationPanel`
- `ToolResultPanel`
- `TracePanel`
- `RecoveryBanner`
- `EmptyState`

第二批补充：

- `MobileSidebarDrawer`
- `SearchChatsInput`
- `ThreadActionsMenu`
- `CopyMessageButton`
- `RetryMessageButton`
- `ThemeTokensPreview`

---

## 11. 分阶段实施计划

## Phase 0：接口盘点与契约冻结

目标：

- 明确前端实际需要哪些字段
- 统一请求与响应结构
- 确保前端开发期间 API 不反复改

任务清单：

- 审查 [app/api/chat.py](/c:/AI_tech/projects/stock_agent/app/api/chat.py:1) 当前输出字段
- 补 `title / plan / trace / created_at`
- 统一历史消息返回结构
- 输出一份简短 `API contract`

完成标准：

- 前端可以不依赖 Streamlit 逻辑直接消费 API

---

## Phase 1：前端工程初始化

目标：

- 建立新前端项目骨架
- 跑通本地开发链路

任务清单：

- 创建 `frontend/`
- 初始化 `Vite + React + TypeScript`
- 安装 `React Router / TanStack Query / Tailwind / Motion / react-markdown / Lucide`
- 配置别名、环境变量、基础 lint
- 建 `src/app/providers.tsx`
- 建基础布局和空路由

完成标准：

- `frontend` 可独立启动
- 能访问后端 `health`

---

## Phase 2：聊天主链路打通

目标：

- 先完成一个可用但未精修视觉的聊天产品

任务清单：

- 首页欢迎区
- 会话列表接口接入
- 新建会话
- 打开发送消息
- 渲染 Markdown 回答
- 删除会话
- 基础 loading、error、empty state

完成标准：

- 用户可以完整地“新建 -> 提问 -> 查看回答 -> 查看历史 -> 删除”

---

## Phase 3：诊断信息与研究辅助面板

目标：

- 把现在 Streamlit 有价值但零散的信息，做成专业侧边面板

任务清单：

- 引用面板
- 工具结果面板
- 执行轨迹面板
- 恢复信息提示条
- 文档统计展示

完成标准：

- 主对话区保持简洁
- 辅助信息可折叠、可浏览、不抢主阅读流

---

## Phase 4：流式输出与体验升级

目标：

- 体验从“问答页”升级成“AI 产品”

任务清单：

- 接入 `SSE` 流式响应
- 实现 token 级或句子级增量渲染
- 输入区发送状态
- 中断与失败重试
- 平滑滚动到底部
- 首屏推荐问题卡片

完成标准：

- 回答不再是整块跳出，而是连续生成
- 体验接近成熟聊天产品

---

## Phase 5：视觉重构

目标：

- 让页面从“工程可用”升级成“产品可展示”

任务清单：

- 建立颜色、间距、圆角、阴影、边框 token
- 做品牌首页
- 优化三栏布局比例
- 优化消息气泡排版
- 优化 hover、focus、loading 动效
- 优化移动端

完成标准：

- 页面第一眼不再像后台工具
- 首页和聊天页有明显产品感

---

## Phase 6：切换与收尾

目标：

- 完成新旧入口切换

任务清单：

- README 增加新启动方式
- 保留 Streamlit 作为临时 debug 入口
- 验证 API 与前端联调
- 明确后续是否彻底下线 Streamlit

完成标准：

- 团队默认使用新前端

---

## 12. 具体开发顺序

建议严格按下面顺序推进：

1. 补 API contract
2. 起 `frontend` 工程
3. 跑通历史会话列表
4. 跑通发送消息和回答展示
5. 跑通会话切换与删除
6. 接入引用和工具结果
7. 接入 `plan / trace / recovery`
8. 做流式输出
9. 做视觉精修
10. 做移动端适配

不要一开始就先做大规模视觉稿，否则很容易在 API 还不稳时返工。

---

## 13. 环境变量建议

后端建议新增：

```bash
FRONTEND_ORIGINS=http://localhost:5173,http://localhost:3000
```

前端建议新增：

```bash
VITE_API_BASE_URL=http://localhost:8000
```

---

## 14. 验收标准

### 功能验收

- 可以新建会话
- 可以查看历史会话
- 可以删除会话
- 可以发送问题并看到回答
- 可以查看资料引用
- 可以查看工具结果与执行轨迹
- 可以正常处理错误状态

### 体验验收

- 首屏有明确产品感
- 聊天输入区固定且易用
- 页面层级清晰
- 辅助信息不干扰主回答阅读
- 移动端可用

### 工程验收

- 前后端本地可独立启动
- API 字段稳定
- 组件边界清晰
- 状态管理不过度耦合

---

## 15. 风险点

### 15.1 最大风险

- 后端 API 输出结构不稳定
- 流式输出改造会牵动 Agent 结果生成方式
- 旧 `Streamlit` 中部分展示字段没有完全 API 化

### 15.2 应对方式

- 先冻结 contract，再开前端
- 第一版允许非流式，第二版再上 `SSE`
- 所有复杂诊断信息统一塞进 `metadata`

---

## 16. 首版里可以先不做的内容

- 登录注册
- 多用户权限
- 文件上传
- 主题切换
- 分享链接
- 富文本编辑器
- 复杂图表工作台

这些都会分散主线，先把聊天研究工作台打磨成型更重要。

---

## 17. 建议的首个交付里程碑

如果只做第一轮可见成果，建议目标定成：

### M1：2 到 4 天内交付

- 新建 `frontend/`
- 跑通聊天主链路
- 有历史会话
- 有比 Streamlit 明显更好的首页和聊天页
- 保留右侧引用面板的基础版本

### M2：随后 2 到 4 天补齐

- 流式输出
- 轨迹与恢复信息
- 移动端适配
- 视觉打磨

---

## 18. 建议的下一步执行

如果马上开工，最合理的顺序是：

1. 先改后端 `app/api/chat.py`，补齐 contract
2. 创建 `frontend/` 项目骨架
3. 先实现静态壳子和布局
4. 再接 API
5. 最后做流式和视觉强化

这条路径返工最少，也最符合当前仓库现状。
