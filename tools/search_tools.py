"""
tools/search_tools.py
---------------------
代码库检索工具集，让 Agent 能在庞大项目中自主定位 Bug。

工具列表：
  - list_directory     : 递归列出目录树结构
  - search_codebase    : 基于 grep（文本正则）全局搜索代码
  - find_definition    : 基于 AST 精准定位函数/类的定义位置
  - grep_in_file       : 在单个文件内搜索匹配行（精细检索）

所有工具遵循规范：
  1. 入参/出参均为基础类型（str / int），方便 LLM 调用
  2. 全部包含 try-except，错误以字符串形式返回，不崩溃
  3. 输出结果做适当截断，防止 LLM 上下文爆炸
"""

import ast
import re
from pathlib import Path
from typing import Optional

from langchain_core.tools import tool

from tools.workspace import resolve_workspace_path

# ── 安全常量 ──────────────────────────────────
# 检索结果最大返回行数，防止输出过大撑爆 LLM context
MAX_SEARCH_RESULTS = 50
# 目录树最大深度
MAX_TREE_DEPTH = 5
# 目录树最大展示条目数
MAX_TREE_ENTRIES = 200

# 默认忽略的目录（不检索）
_IGNORE_DIRS = {
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".eggs",
    "*.egg-info",
}

# 默认检索的文件后缀（可通过参数覆盖）
_DEFAULT_EXTENSIONS = {".py", ".md", ".txt", ".toml", ".yaml", ".yml", ".json"}


def _should_ignore(path: Path) -> bool:
    """判断路径是否应该被忽略（在隐藏目录或黑名单目录中）。"""
    for part in path.parts:
        if part in _IGNORE_DIRS or part.startswith("."):
            return True
    return False


# ──────────────────────────────────────────────
# 工具 1：列出目录结构
# ──────────────────────────────────────────────
@tool
def list_directory(
    directory_path: str = ".",
    max_depth: int = 3,
) -> str:
    """
    递归列出指定目录的树状结构，帮助 Agent 快速了解项目布局。

    自动跳过 .git、.venv、__pycache__ 等无关目录。

    Args:
        directory_path: 要列出的目录路径（默认为当前目录 "."）。
        max_depth:       最大递归深度，范围 1-5（默认 3）。

    Returns:
        树状目录结构字符串；出错时返回错误描述。
    """
    print(f"  [Tool: list_directory] 列出目录: {directory_path}（深度={max_depth}）")
    try:
        root = resolve_workspace_path(directory_path).resolve()
        if not root.exists():
            return f"[错误] 目录不存在: {directory_path}"
        if not root.is_dir():
            return f"[错误] 路径不是目录: {directory_path}"

        max_depth = max(1, min(max_depth, MAX_TREE_DEPTH))
        lines: list[str] = [f"{root}/"]
        entry_count = 0

        def _walk(path: Path, depth: int, prefix: str) -> None:
            nonlocal entry_count
            if depth > max_depth or entry_count >= MAX_TREE_ENTRIES:
                return

            try:
                # 排序：目录在前，文件在后，字母排序
                entries = sorted(
                    path.iterdir(),
                    key=lambda p: (not p.is_dir(), p.name.lower()),
                )
            except PermissionError:
                lines.append(f"{prefix}└── [权限拒绝]")
                return

            for i, entry in enumerate(entries):
                if _should_ignore(entry):
                    continue
                if entry_count >= MAX_TREE_ENTRIES:
                    lines.append(f"{prefix}└── ... (条目过多，已截断)")
                    break

                is_last = i == len(entries) - 1
                connector = "└── " if is_last else "├── "
                suffix = "/" if entry.is_dir() else ""
                lines.append(f"{prefix}{connector}{entry.name}{suffix}")
                entry_count += 1

                if entry.is_dir():
                    extension = "    " if is_last else "│   "
                    _walk(entry, depth + 1, prefix + extension)

        _walk(root, 1, "")
        result = "\n".join(lines)
        print(f"  [Tool: list_directory] 完成，共 {entry_count} 条目")
        return result

    except Exception as e:
        error_msg = f"[错误] list_directory 执行失败: {type(e).__name__}: {e}"
        print(f"  [Tool: list_directory] {error_msg}")
        return error_msg


# ──────────────────────────────────────────────
# 工具 2：全局代码库文本检索（基于 grep）
# ──────────────────────────────────────────────
@tool
def search_codebase(
    pattern: str,
    directory_path: str = ".",
    file_extension: str = ".py",
    case_sensitive: bool = False,
) -> str:
    """
    在指定目录下递归搜索匹配正则表达式的代码行（类似 grep -rn）。

    适合场景：
      - 查找某个函数/变量在哪些文件里被调用
      - 定位错误字符串或特定 import
      - 搜索 TODO / FIXME 注释

    Args:
        pattern:        正则表达式或普通字符串，例如 "def calculate" 或 "import os"。
        directory_path: 搜索根目录（默认 "."）。
        file_extension: 只搜索该后缀的文件（默认 ".py"，传 "" 表示搜索所有文件）。
        case_sensitive: 是否区分大小写（默认 False，不区分）。

    Returns:
        匹配结果字符串，格式为 "文件路径:行号: 代码行内容"；
        未找到返回提示；出错返回错误描述。
    """
    print(f"  [Tool: search_codebase] 搜索 '{pattern}' in '{directory_path}' (*{file_extension})")
    try:
        root = resolve_workspace_path(directory_path).resolve()
        if not root.exists():
            return f"[错误] 目录不存在: {directory_path}"

        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            compiled_pattern = re.compile(pattern, flags)
        except re.error as e:
            return f"[错误] 无效的正则表达式 '{pattern}': {e}"

        matches: list[str] = []

        for filepath in sorted(root.rglob(f"*{file_extension}" if file_extension else "*")):
            if not filepath.is_file():
                continue
            if _should_ignore(filepath.relative_to(root)):
                continue
            if len(matches) >= MAX_SEARCH_RESULTS:
                matches.append(f"... (结果超过 {MAX_SEARCH_RESULTS} 条，已截断，请缩小搜索范围)")
                break

            try:
                content = filepath.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue

            for lineno, line in enumerate(content.splitlines(), start=1):
                if compiled_pattern.search(line):
                    rel_path = filepath.relative_to(root)
                    matches.append(f"{rel_path}:{lineno}: {line.rstrip()}")
                    if len(matches) >= MAX_SEARCH_RESULTS:
                        break

        if not matches:
            return f"[无结果] 在 '{directory_path}' 中未找到匹配 '{pattern}' 的 {file_extension} 文件内容"

        result = "\n".join(matches)
        print(f"  [Tool: search_codebase] 找到 {len(matches)} 条匹配")
        return result

    except Exception as e:
        error_msg = f"[错误] search_codebase 执行失败: {type(e).__name__}: {e}"
        print(f"  [Tool: search_codebase] {error_msg}")
        return error_msg


# ──────────────────────────────────────────────
# 工具 3：AST 精准定位函数/类定义
# ──────────────────────────────────────────────
@tool
def find_definition(
    symbol_name: str,
    directory_path: str = ".",
) -> str:
    """
    使用 Python AST（抽象语法树）在代码库中精准定位函数或类的定义位置。

    与 search_codebase 的区别：
      - search_codebase 是文本搜索，会包含注释、字符串中的误匹配
      - find_definition 解析 AST，只返回真正的函数/类定义，精确且无噪声

    适合场景：
      - 确认某函数是否存在及其所在文件
      - 找到类定义位置后再用 read_file 读取完整实现
      - 查看函数参数签名

    Args:
        symbol_name:    要查找的函数名或类名（精确匹配，不支持正则）。
        directory_path: 搜索根目录（默认 "."）。

    Returns:
        所有匹配的定义位置，格式为 "文件路径:行号: def/class 签名"；
        未找到时返回提示；出错返回错误描述。
    """
    print(f"  [Tool: find_definition] 查找符号 '{symbol_name}' in '{directory_path}'")
    try:
        root = resolve_workspace_path(directory_path).resolve()
        if not root.exists():
            return f"[错误] 目录不存在: {directory_path}"

        results: list[str] = []

        for filepath in sorted(root.rglob("*.py")):
            if not filepath.is_file():
                continue
            if _should_ignore(filepath.relative_to(root)):
                continue

            try:
                source = filepath.read_text(encoding="utf-8", errors="ignore")
                tree = ast.parse(source, filename=str(filepath))
            except SyntaxError:
                # 跳过语法错误文件，不中断整体检索
                continue
            except Exception:
                continue

            for node in ast.walk(tree):
                # 匹配函数定义（普通函数 & 异步函数）和类定义
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if node.name == symbol_name:
                        rel_path = filepath.relative_to(root)
                        # 提取参数签名（仅函数）
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            args = [arg.arg for arg in node.args.args]
                            kind = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                            signature = f"{kind} {node.name}({', '.join(args)})"
                        else:
                            bases = [ast.unparse(b) for b in node.bases] if node.bases else []
                            signature = f"class {node.name}({', '.join(bases)})" if bases else f"class {node.name}"

                        results.append(f"{rel_path}:{node.lineno}: {signature}")

        if not results:
            return f"[无结果] 未找到符号 '{symbol_name}' 的定义（已搜索 {directory_path} 下所有 .py 文件）"

        result = "\n".join(results)
        print(f"  [Tool: find_definition] 找到 {len(results)} 处定义")
        return result

    except Exception as e:
        error_msg = f"[错误] find_definition 执行失败: {type(e).__name__}: {e}"
        print(f"  [Tool: find_definition] {error_msg}")
        return error_msg


# ──────────────────────────────────────────────
# 工具 4：在单个文件内精细搜索
# ──────────────────────────────────────────────
@tool
def grep_in_file(
    file_path: str,
    pattern: str,
    context_lines: int = 3,
) -> str:
    """
    在单个文件内搜索匹配行，并返回每个匹配的上下文代码（前后 N 行）。

    适合场景：
      - 已知 Bug 所在文件，需要精确定位有问题的代码段
      - 查看某变量赋值或函数调用的完整上下文

    Args:
        file_path:     要搜索的文件路径。
        pattern:       正则表达式或普通字符串。
        context_lines: 每个匹配项显示的上下文行数（默认 3，最大 10）。

    Returns:
        带行号和上下文的匹配结果；未找到返回提示；出错返回错误描述。
    """
    print(f"  [Tool: grep_in_file] 在 '{file_path}' 中搜索 '{pattern}'")
    try:
        path = resolve_workspace_path(file_path)
        if not path.exists():
            return f"[错误] 文件不存在: {file_path}"
        if not path.is_file():
            return f"[错误] 路径不是文件: {file_path}"

        context_lines = max(0, min(context_lines, 10))

        try:
            compiled_pattern = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return f"[错误] 无效的正则表达式 '{pattern}': {e}"

        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        total_lines = len(lines)

        # 收集所有匹配行的行号（1-indexed）
        match_linenos = [
            i + 1 for i, line in enumerate(lines)
            if compiled_pattern.search(line)
        ]

        if not match_linenos:
            return f"[无结果] 文件 '{file_path}' 中未找到匹配 '{pattern}' 的内容"

        # 合并重叠的上下文窗口，避免重复输出
        segments: list[tuple[int, int]] = []
        for lineno in match_linenos:
            start = max(1, lineno - context_lines)
            end = min(total_lines, lineno + context_lines)
            if segments and start <= segments[-1][1] + 1:
                segments[-1] = (segments[-1][0], end)  # 合并
            else:
                segments.append((start, end))

        output_parts: list[str] = []
        for seg_start, seg_end in segments:
            output_parts.append(f"--- 行 {seg_start}-{seg_end} ---")
            for i in range(seg_start - 1, seg_end):
                lineno = i + 1
                marker = ">>>" if lineno in match_linenos else "   "
                output_parts.append(f"{marker} {lineno:4d} | {lines[i]}")

        result = "\n".join(output_parts)
        print(f"  [Tool: grep_in_file] 找到 {len(match_linenos)} 处匹配，{len(segments)} 个代码段")
        return result

    except Exception as e:
        error_msg = f"[错误] grep_in_file 执行失败: {type(e).__name__}: {e}"
        print(f"  [Tool: grep_in_file] {error_msg}")
        return error_msg
