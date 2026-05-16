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

import logging

logger = logging.getLogger(__name__)

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
    Recursively list a directory tree to help the agent quickly understand the project layout.

    Automatically skips .git, .venv, __pycache__, and other irrelevant directories.

    Args:
        directory_path: Directory to list (default ".").
        max_depth:       Maximum recursion depth, 1-5 (default 3).

    Returns:
        Tree-structured directory string; error description on failure.
    """
    logger.debug(f"  [Tool: list_directory] listing: {directory_path} (depth={max_depth})")
    try:
        root = resolve_workspace_path(directory_path).resolve()
        if not root.exists():
            return f"[ERROR] Directory not found: {directory_path}"
        if not root.is_dir():
            return f"[ERROR] Path is not a directory: {directory_path}"

        max_depth = max(1, min(max_depth, MAX_TREE_DEPTH))
        lines: list[str] = [f"{root}/"]
        entry_count = 0

        def _walk(path: Path, depth: int, prefix: str) -> None:
            nonlocal entry_count
            if depth > max_depth or entry_count >= MAX_TREE_ENTRIES:
                return

            try:
                entries = sorted(
                    path.iterdir(),
                    key=lambda p: (not p.is_dir(), p.name.lower()),
                )
            except PermissionError:
                lines.append(f"{prefix}└── [permission denied]")
                return

            for i, entry in enumerate(entries):
                if _should_ignore(entry):
                    continue
                if entry_count >= MAX_TREE_ENTRIES:
                    lines.append(f"{prefix}└── ... (too many entries, truncated)")
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
        logger.debug(f"  [Tool: list_directory] done, {entry_count} entries")
        return result

    except Exception as e:
        error_msg = f"[ERROR] list_directory failed: {type(e).__name__}: {e}"
        logger.error(f"  [Tool: list_directory] {error_msg}")
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
    Recursively search for lines matching a regex pattern across a directory (like grep -rn).

    Useful for:
      - Finding where a function or variable is called
      - Locating a specific import or error string
      - Searching for TODO / FIXME comments

    Args:
        pattern:        Regex or plain string, e.g. "def calculate" or "import os".
        directory_path: Root directory to search (default ".").
        file_extension: Only search files with this extension (default ".py"; pass "" for all files).
        case_sensitive: Whether the search is case-sensitive (default False).

    Returns:
        Matches as "file:lineno: line content"; no-results message if nothing found; error description on failure.
    """
    logger.debug(f"  [Tool: search_codebase] searching '{pattern}' in '{directory_path}' (*{file_extension})")
    try:
        root = resolve_workspace_path(directory_path).resolve()
        if not root.exists():
            return f"[ERROR] Directory not found: {directory_path}"

        flags = 0 if case_sensitive else re.IGNORECASE
        try:
            compiled_pattern = re.compile(pattern, flags)
        except re.error as e:
            return f"[ERROR] Invalid regex '{pattern}': {e}"

        matches: list[str] = []

        for filepath in sorted(root.rglob(f"*{file_extension}" if file_extension else "*")):
            if not filepath.is_file():
                continue
            if _should_ignore(filepath.relative_to(root)):
                continue
            if len(matches) >= MAX_SEARCH_RESULTS:
                matches.append(f"... (over {MAX_SEARCH_RESULTS} results, truncated — narrow your search)")
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
            return f"[NO RESULTS] No {file_extension} content matching '{pattern}' found in '{directory_path}'"

        result = "\n".join(matches)
        logger.debug(f"  [Tool: search_codebase] found {len(matches)} matches")
        return result

    except Exception as e:
        error_msg = f"[ERROR] search_codebase failed: {type(e).__name__}: {e}"
        logger.error(f"  [Tool: search_codebase] {error_msg}")
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
    Use Python AST to precisely locate function or class definitions in the codebase.

    Unlike search_codebase:
      - search_codebase does text search, which may include false matches in comments or strings
      - find_definition parses the AST, returning only real function/class definitions — precise and noise-free

    Useful for:
      - Confirming whether a function exists and which file it is in
      - Locating a class definition before reading the full implementation with read_file
      - Viewing a function's parameter signature

    Args:
        symbol_name:    Exact function or class name to find (no regex).
        directory_path: Root directory to search (default ".").

    Returns:
        All matching definitions as "file:lineno: def/class signature"; no-results message if not found; error description on failure.
    """
    logger.debug(f"  [Tool: find_definition] searching symbol '{symbol_name}' in '{directory_path}'")
    try:
        root = resolve_workspace_path(directory_path).resolve()
        if not root.exists():
            return f"[ERROR] Directory not found: {directory_path}"

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
                continue
            except Exception:
                continue

            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    if node.name == symbol_name:
                        rel_path = filepath.relative_to(root)
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            args = [arg.arg for arg in node.args.args]
                            kind = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
                            signature = f"{kind} {node.name}({', '.join(args)})"
                        else:
                            bases = [ast.unparse(b) for b in node.bases] if node.bases else []
                            signature = f"class {node.name}({', '.join(bases)})" if bases else f"class {node.name}"

                        results.append(f"{rel_path}:{node.lineno}: {signature}")

        if not results:
            return f"[NO RESULTS] Symbol '{symbol_name}' not found (searched all .py files under {directory_path})"

        result = "\n".join(results)
        logger.debug(f"  [Tool: find_definition] found {len(results)} definitions")
        return result

    except Exception as e:
        error_msg = f"[ERROR] find_definition failed: {type(e).__name__}: {e}"
        logger.error(f"  [Tool: find_definition] {error_msg}")
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
    Search for matching lines within a single file and return each match with surrounding context (N lines before/after).

    Useful for:
      - Precisely locating a problematic code segment when the file is already known
      - Viewing the full context of a variable assignment or function call

    Args:
        file_path:     Path to the file to search.
        pattern:       Regex or plain string.
        context_lines: Lines of context to show around each match (default 3, max 10).

    Returns:
        Matches with line numbers and context; no-results message if nothing found; error description on failure.
    """
    logger.debug(f"  [Tool: grep_in_file] searching '{pattern}' in '{file_path}'")
    try:
        path = resolve_workspace_path(file_path)
        if not path.exists():
            return f"[ERROR] File not found: {file_path}"
        if not path.is_file():
            return f"[ERROR] Path is not a file: {file_path}"

        context_lines = max(0, min(context_lines, 10))

        try:
            compiled_pattern = re.compile(pattern, re.IGNORECASE)
        except re.error as e:
            return f"[ERROR] Invalid regex '{pattern}': {e}"

        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        total_lines = len(lines)

        match_linenos = [
            i + 1 for i, line in enumerate(lines)
            if compiled_pattern.search(line)
        ]

        if not match_linenos:
            return f"[NO RESULTS] No content matching '{pattern}' found in '{file_path}'"

        segments: list[tuple[int, int]] = []
        for lineno in match_linenos:
            start = max(1, lineno - context_lines)
            end = min(total_lines, lineno + context_lines)
            if segments and start <= segments[-1][1] + 1:
                segments[-1] = (segments[-1][0], end)
            else:
                segments.append((start, end))

        output_parts: list[str] = []
        for seg_start, seg_end in segments:
            output_parts.append(f"--- lines {seg_start}-{seg_end} ---")
            for i in range(seg_start - 1, seg_end):
                lineno = i + 1
                marker = ">>>" if lineno in match_linenos else "   "
                output_parts.append(f"{marker} {lineno:4d} | {lines[i]}")

        result = "\n".join(output_parts)
        logger.debug(f"  [Tool: grep_in_file] found {len(match_linenos)} matches in {len(segments)} segments")
        return result

    except Exception as e:
        error_msg = f"[ERROR] grep_in_file failed: {type(e).__name__}: {e}"
        logger.error(f"  [Tool: grep_in_file] {error_msg}")
        return error_msg
