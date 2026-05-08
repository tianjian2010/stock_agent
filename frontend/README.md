# Frontend

`frontend/` 是当前默认产品入口，对接仓库中的 `FastAPI` 后端。

## 技术栈

- React 19
- TypeScript
- Vite
- React Router
- TanStack Query
- Tailwind CSS

## 本地启动

1. 安装依赖

```bash
npm install
```

2. 配置接口地址

在 `frontend/.env` 中设置：

```bash
VITE_API_BASE_URL=http://localhost:8000
```

3. 启动开发环境

```bash
npm run dev
```

默认地址：`http://localhost:5173`

## 构建

```bash
npm run build
```

说明：当前 Windows 环境使用了 `vite build --configLoader native`，已经内置在 `package.json` 中。

## 当前范围

- 首页引导
- 聊天主界面
- 会话历史
- 引用 / 工具 / 轨迹 / 恢复面板
- 流式状态反馈
- 移动端基础可用性
