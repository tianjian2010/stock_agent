#!/usr/bin/env python3
"""
GitMan - Git 管理脚本
支持显式命令和意图驱动的 Git 操作
"""

import argparse
import subprocess
import sys
import os
import re
from typing import Optional, Tuple

# 危险操作列表
DANGEROUS_OPERATIONS = {'push --force', 'push -f', 'reset --hard', 'reset -h', 'checkout -f', 'clean -f'}


def is_dangerous(args: list) -> bool:
    """检查是否包含危险操作"""
    cmd_str = ' '.join(args)
    return any(dangerous in cmd_str for dangerous in DANGEROUS_OPERATIONS)


def run_git_command(args: list, capture: bool = True) -> Tuple[int, str, str]:
    """执行 git 命令"""
    cmd = ['git'] + args
    try:
        if capture:
            result = subprocess.run(cmd, capture_output=True, text=True, shell=True)
            return result.returncode, result.stdout, result.stderr
        else:
            result = subprocess.run(cmd, shell=True)
            return result.returncode, '', ''
    except Exception as e:
        return 1, '', str(e)


def get_current_branch() -> str:
    """获取当前分支名"""
    _, stdout, _ = run_git_command(['branch', '--show-current'])
    return stdout.strip()


def get_status() -> str:
    """获取工作区状态"""
    _, stdout, stderr = run_git_command(['status', '--porcelain'])
    if stderr:
        return f"Error: {stderr}"
    if not stdout.strip():
        return "Working tree clean"
    return f"Changes:\n{stdout}"


def do_add(files: Optional[list] = None) -> str:
    """执行 git add"""
    if not files:
        _, stdout, _ = run_git_command(['status', '--porcelain'])
        files = [line[3:] for line in stdout.strip().split('\n') if line.strip()]
        if not files:
            return "No files to stage"
    _, stdout, stderr = run_git_command(['add'] + files)
    if stderr:
        return f"Error: {stderr}"
    return f"Staged: {', '.join(files)}"


def do_commit(message: str) -> str:
    """执行 git commit"""
    if not message:
        return "Please provide commit message: /gitman commit -m 'message'"
    _, stdout, stderr = run_git_command(['commit', '-m', message])
    if stderr:
        return f"Error: {stderr}"
    return stdout if stdout else "Commit successful"


def do_push(force: bool = False) -> Tuple[str, bool]:
    """执行 git push"""
    args = ['push']
    if force:
        args.extend(['--force'])
    _, stdout, stderr = run_git_command(args)
    if stderr:
        return f"Error: {stderr}", False
    output = stdout if stdout else "Push successful"
    return output, force


def do_pull() -> str:
    """执行 git pull"""
    _, stdout, stderr = run_git_command(['pull'])
    if stderr:
        return f"Error: {stderr}"
    return stdout if stdout else "Pull successful"


def do_status() -> str:
    """执行 git status"""
    _, stdout, stderr = run_git_command(['status'])
    if stderr:
        return f"Error: {stderr}"
    return stdout


def do_log(n: int = 10) -> str:
    """执行 git log"""
    _, stdout, stderr = run_git_command(['log', f'-{n}', '--oneline', '--decorate'])
    if stderr:
        return f"Error: {stderr}"
    return stdout if stdout else "No commit history"


def do_branch(operation: str) -> str:
    """执行 git branch"""
    _, stdout, stderr = run_git_command(['branch', '-a'])
    if stderr:
        return f"Error: {stderr}"
    return stdout if stdout else "Done"


def do_checkout(branch: str, force: bool = False) -> Tuple[str, bool]:
    """执行 git checkout"""
    args = ['checkout']
    if force:
        args.append('-f')
    args.append(branch)
    _, stdout, stderr = run_git_command(args)
    if stderr:
        return f"Error: {stderr}", force
    return stdout if stdout else f"Switched to {branch}", force


def do_init(repo_path: Optional[str] = None) -> str:
    """执行 git init"""
    args = ['init']
    if repo_path:
        args.append(repo_path)
    _, stdout, stderr = run_git_command(args)
    if stderr:
        return f"Error: {stderr}"
    path_msg = f" in {repo_path}" if repo_path else ""
    return f"Initialized empty Git repository{path_msg}"
    """执行 git diff"""
    _, stdout, stderr = run_git_command(['diff', '--stat'])
    if stderr:
        return f"Error: {stderr}"
    return stdout if stdout else "No changes"


def parse_intent(user_input: str) -> Tuple[str, dict]:
    """解析自然语言意图"""
    user_input_lower = user_input.lower().strip()

    # 提交相关
    commit_phrases = ['提交', 'commit', '提交代码']
    if any(phrase in user_input_lower for phrase in commit_phrases):
        # Try to extract commit message from quotes or after colon
        quotes = re.findall(r'"([^"]+)"|\'([^\']+)\'', user_input)
        for q in quotes:
            for g in q:
                if g:
                    message = g
                    return 'intent_commit', {'message': message}
        # Try colon separator
        colon_match = re.search(r'[:：]\s*(.+)', user_input)
        if colon_match:
            message = colon_match.group(1).strip()
            return 'intent_commit', {'message': message}
        return 'intent_commit', {'message': 'update'}

    # 推送相关
    push_phrases = ['推送', 'push', '推送到']
    if any(phrase in user_input_lower for phrase in push_phrases):
        return 'intent_push', {}

    # 拉取相关
    pull_phrases = ['拉取', 'pull', '更新']
    if any(phrase in user_input_lower for phrase in pull_phrases):
        return 'intent_pull', {}

    # 查看状态
    status_phrases = ['状态', 'status', '查看情况']
    if any(phrase in user_input_lower for phrase in status_phrases):
        return 'intent_status', {}

    # 查看历史
    log_phrases = ['历史', 'log', '提交记录']
    if any(phrase in user_input_lower for phrase in log_phrases):
        return 'intent_log', {}

    # 分支
    branch_phrases = ['分支', 'branch']
    if any(phrase in user_input_lower for phrase in branch_phrases):
        return 'intent_branch', {}

    return 'unknown', {}


def handle_intent(intent: str, params: dict) -> Tuple[str, Optional[bool]]:
    """处理意图驱动的命令"""
    if intent == 'intent_commit':
        result = do_add()
        if "No files" in result:
            return result, None
        result += "\n" + do_commit(params.get('message', 'update'))
        return result, None

    elif intent == 'intent_push':
        return do_push(force=False)

    elif intent == 'intent_pull':
        return do_pull(), None

    elif intent == 'intent_status':
        return get_status(), None

    elif intent == 'intent_log':
        return do_log(), None

    elif intent == 'intent_branch':
        return do_branch('list'), None

    return "Cannot understand intent", None


def main():
    parser = argparse.ArgumentParser(description='GitMan - Git Helper')
    parser.add_argument('command', nargs='?', help='Command or intent')
    parser.add_argument('-m', '--message', help='commit message')
    parser.add_argument('-f', '--force', action='store_true', help='Force execution')
    parser.add_argument('-n', '--number', type=int, default=10, help='Display count')
    parser.add_argument('files', nargs='*', help='File list')
    parser.add_argument('--dangerous-confirm', action='store_true', help='Confirm dangerous operation')

    args = parser.parse_args()

    # No args show help
    if not args.command:
        print("GitMan - Git Helper")
        print("\nUsage:")
        print("  /gitman init [path]     Initialize repository")
        print("  /gitman status          View status")
        print("  /gitman add <files>     Stage files")
        print("  /gitman commit -m <msg> Commit")
        print("  /gitman push            Push")
        print("  /gitman pull            Pull")
        print("  /gitman log             View history")
        print("  /gitman branch          View branches")
        print("\nNatural language:")
        print("  /gitman 提交代码")
        print("  /gitman 推送代码")
        return

    # Check if in git repo
    rc, _, _ = run_git_command(['rev-parse', '--git-dir'], capture=True)
    if rc != 0:
        print("Error: Not a git repository")
        sys.exit(1)

    # Intent mode detection
    valid_commands = ['status', 'add', 'commit', 'push', 'pull', 'log', 'branch', 'checkout', 'diff', 'fetch', 'reset', 'clean', 'init']
    if args.command not in valid_commands:
        intent, params = parse_intent(args.command)
        if intent != 'unknown':
            output, dangerous = handle_intent(intent, params)
            print(output)
            sys.exit(0)
        print(f"Unknown command: {args.command}")
        sys.exit(1)

    # Explicit command handling
    cmd = args.command.lower()
    result = ""
    dangerous = False

    if cmd == 'status':
        result = do_status()

    elif cmd == 'add':
        result = do_add(args.files if args.files else None)

    elif cmd == 'commit':
        if not args.message:
            print("Please provide -m for commit message")
            sys.exit(1)
        do_add(args.files if args.files else None)
        result = do_commit(args.message)

    elif cmd == 'push':
        result, dangerous = do_push(force=args.force)

    elif cmd == 'pull':
        result = do_pull()

    elif cmd == 'log':
        result = do_log(args.number)

    elif cmd == 'branch':
        result = do_branch('list')

    elif cmd == 'checkout':
        if not args.files:
            print("Please specify branch name")
            sys.exit(1)
        result, dangerous = do_checkout(args.files[0], force=args.force)

    elif cmd == 'diff':
        result = do_diff()

    elif cmd == 'init':
        result = do_init(args.files[0] if args.files else None)

    elif cmd == 'fetch':
        _, result, _ = run_git_command(['fetch'])
        result = result or "Fetch done"

    elif cmd == 'reset':
        if not args.force:
            result = "Use --force to confirm hard reset"
            dangerous = True
        else:
            result = "Hard reset (warning: will lose uncommitted changes)"
            dangerous = True

    elif cmd == 'clean':
        if not args.force:
            result = "Use --force to confirm force clean"
            dangerous = True
        else:
            result = "Force clean (warning: will delete untracked files)"
            dangerous = True

    # Dangerous operation confirmation
    if dangerous and not args.dangerous_confirm:
        print(f"Warning: {result}")
        print("Add --dangerous-confirm to confirm")
        sys.exit(1)

    print(result)


if __name__ == '__main__':
    main()