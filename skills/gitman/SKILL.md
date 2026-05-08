---
name: gitman
description: Git 管理技能，支持自动执行 git add、commit、push、pull、branch、status 等基础命令。混合模式：可自然语言交互（如"提交代码"）或显式指定命令。危险操作（force push、reset 等）会二次确认。
---

# Git 管理 (gitman)

自动化的 Git 版本控制助手，支持基础命令和意图驱动的操作。

## 支持的命令

### 显式命令
- `git init [path]` - 初始化新 Git 仓库
- `git status` - 查看工作区状态
- `git add <files>` - 暂存文件
- `git commit -m <msg>` - 提交更改
- `git push` - 推送到远程
- `git pull` - 拉取远程更新
- `git branch` - 查看/管理分支
- `git checkout <branch>` - 切换分支
- `git log` - 查看提交历史
- `git diff` - 查看变更
- `git fetch` - 获取远程元信息

### 意图驱动（自然语言）
- "提交代码" / "commit" → 自动暂存并提交
- "推送代码" / "push" → 推送到当前分支
- "拉取更新" / "pull" → 拉取并合并
- "查看状态" → git status
- "查看历史" → git log

## 使用方式

### 显式命令
```
/gitman commit -m "fix: 修复登录bug"
/gitman push
/gitman status
```

### 自然语言
```
/gitman 帮我提交代码
/gitman 把修改推送到远程
/gitman 查看最近的提交
```

## 危险操作确认

以下操作需要用户明确确认：
- `git push --force` - 强制推送
- `git reset --hard` - 硬重置
- `git checkout -f` - 强制切换
- `git clean -f` - 强制清理

## 工作流程

1. 用户输入命令或意图
2. 解析命令并执行
3. 返回执行结果
4. 危险操作执行前请求确认

## 注意事项

- 仅在 Git 仓库根目录执行
- commit message 默认格式：`feat/fix/docs/chore: 描述`
- 自动检测当前分支名称