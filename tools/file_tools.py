"""
tools/file_tools.py
-------------------
本地文件系统操作工具集。

所有工具使用 @tool 装饰器，遵循以下规范：
  1. 入参/出参均为基础类型，方便 LLM 调用
  2. 所有文件 IO 操作必须包裹在 try-except 中
  3. 错误不崩溃，而是将错误信息 return 给 LLM，由 LLM 决策后续处理
"""

from pathlib import Path
from typing import Optional

from langchain_core.tools import tool

from tools.workspace import resolve_workspace_path

import logging

logger = logging.getLogger(__name__)

# ── 测试文件保护 ─────────────────────────────
import re

_TEST_PATH_PATTERN = re.compile(
    r"(^|/)tests?/|/test_[^/]+\.py$|_test\.py$",
)


def _is_test_file(file_path: str) -> bool:
    """判断路径是否指向测试文件（tests/ 目录或 test_*.py 文件）。"""
    return bool(_TEST_PATH_PATTERN.search(file_path))


# ──────────────────────────────────────────────
# 工具 1：读取文件
# ──────────────────────────────────────────────
@tool
def read_file(file_path: str) -> str:
    """
    Read the contents of a file at the given path and return it as a string.

    Args:
        file_path: Path to the file (relative or absolute).

    Returns:
        File contents as a string; if the file does not exist or cannot be read, returns an error description.
    """
    logger.debug(f"  [Tool: read_file] reading file: {file_path}")
    try:
        path = resolve_workspace_path(file_path)
        if not path.exists():
            error_msg = f"[ERROR] File not found: {file_path}"
            logger.debug(f"  [Tool: read_file] {error_msg}")
            return error_msg

        if not path.is_file():
            error_msg = f"[ERROR] Path exists but is not a file: {file_path}"
            logger.debug(f"  [Tool: read_file] {error_msg}")
            return error_msg

        content = path.read_text(encoding="utf-8")
        logger.debug(f"  [Tool: read_file] read successfully, length: {len(content)} chars")
        return content

    except PermissionError:
        error_msg = f"[ERROR] Permission denied reading file: {file_path}"
        logger.error(f"  [Tool: read_file] {error_msg}")
        return error_msg
    except Exception as e:
        error_msg = f"[ERROR] Unknown error reading file: {type(e).__name__}: {e}"
        logger.error(f"  [Tool: read_file] {error_msg}")
        return error_msg


# ──────────────────────────────────────────────
# 工具 2：覆盖写入 / 创建文件
# ──────────────────────────────────────────────
@tool
def write_and_replace_file(file_path: str, content: str) -> str:
    """
    Write content to a file. Overwrites if the file exists; creates it (including parent directories) if it does not.

    Args:
        file_path: Target file path (relative or absolute).
        content:   Complete file content to write.

    Returns:
        Confirmation message on success; error description on failure.
    """
    logger.debug(f"  [Tool: write_and_replace_file] writing file: {file_path}")

    if _is_test_file(file_path):
        msg = (
            f"[REJECTED] Modifying test files is not allowed: {file_path}.\n"
            "You must not create or modify any test files. Adjust your source code fix to pass the existing tests.\n"
            "If the existing tests depend on old behavior, ensure your fix is compatible with that behavior, or handle both cases in the source."
        )
        logger.warning(f"  [Tool: write_and_replace_file] rejected write to test file")
        return msg

    try:
        path = resolve_workspace_path(file_path)

        path.parent.mkdir(parents=True, exist_ok=True)

        path.write_text(content, encoding="utf-8")

        written_size = path.stat().st_size
        logger.info(f"  [Tool: write_and_replace_file] write successful, size: {written_size} bytes")
        return f"[OK] File written: {file_path} ({written_size} bytes)"

    except PermissionError:
        error_msg = f"[ERROR] Permission denied writing file: {file_path}"
        logger.error(f"  [Tool: write_and_replace_file] {error_msg}")
        return error_msg
    except OSError as e:
        error_msg = f"[ERROR] Filesystem error: {type(e).__name__}: {e}"
        logger.error(f"  [Tool: write_and_replace_file] {error_msg}")
        return error_msg
    except Exception as e:
        error_msg = f"[ERROR] Unknown error writing file: {type(e).__name__}: {e}"
        logger.error(f"  [Tool: write_and_replace_file] {error_msg}")
        return error_msg


# ──────────────────────────────────────────────
# 工具 3：精确编辑文件（局部替换）
# ──────────────────────────────────────────────
@tool
def edit_file(file_path: str, old_string: str, new_string: str) -> str:
    """
    Perform a precise in-place text replacement in an existing file. old_string must match exactly once.

    This is the preferred tool for modifying existing files — provide only the original snippet and the replacement;
    no need to output the entire file. Works for files of any size.

    Note: If old_string appears more than once, the tool will refuse and return an error.
    In that case, include more surrounding context (e.g. adjacent lines) to make it unique.

    Args:
        file_path:   Path to the file to edit (relative or absolute).
        old_string:  The original text to replace (must match exactly once, including indentation and whitespace).
        new_string:  The replacement text.

    Returns:
        Confirmation message on success; error description on failure.
    """
    logger.debug(f"  [Tool: edit_file] editing file: {file_path}")

    if _is_test_file(file_path):
        msg = (
            f"[REJECTED] Modifying test files is not allowed: {file_path}.\n"
            "You must not modify any test files. Adjust your source code fix to pass the existing tests.\n"
            "If the existing tests depend on old behavior, ensure your fix is compatible with that behavior, or handle both cases in the source."
        )
        logger.warning(f"  [Tool: edit_file] rejected edit of test file")
        return msg

    try:
        path = resolve_workspace_path(file_path)

        if not path.exists():
            error_msg = f"[ERROR] File not found: {file_path}"
            logger.debug(f"  [Tool: edit_file] {error_msg}")
            return error_msg

        if not path.is_file():
            error_msg = f"[ERROR] Path is not a file: {file_path}"
            logger.debug(f"  [Tool: edit_file] {error_msg}")
            return error_msg

        content = path.read_text(encoding="utf-8")

        if old_string == new_string:
            return "[NOTE] old_string and new_string are identical; no change made."

        if old_string not in content:
            preview = content[:500] + "..." if len(content) > 500 else content
            error_msg = (
                f"[ERROR] Text to replace not found in {file_path}.\n"
                f"Make sure old_string exactly matches the file content (including indentation, blank lines, and whitespace).\n"
                f"First 500 chars of file:\n{preview}"
            )
            logger.debug(f"  [Tool: edit_file] old_string not matched")
            return error_msg

        count = content.count(old_string)
        if count > 1:
            error_msg = (
                f"[ERROR] old_string appears {count} times in the file; cannot determine which occurrence to replace. Edit aborted.\n"
                f"Include more surrounding context (e.g. adjacent lines) in old_string to make it unique.\n"
                f"To edit multiple locations, call edit_file separately for each with enough context to uniquely identify it."
            )
            logger.debug(f"  [Tool: edit_file] old_string appears {count} times, refusing")
            return error_msg

        new_content = content.replace(old_string, new_string, 1)
        path.write_text(new_content, encoding="utf-8")

        written_size = path.stat().st_size
        logger.info(f"  [Tool: edit_file] edit successful, size: {written_size} bytes")
        return f"[OK] File edited: {file_path} ({written_size} bytes)"

    except PermissionError:
        error_msg = f"[ERROR] Permission denied editing file: {file_path}"
        logger.error(f"  [Tool: edit_file] {error_msg}")
        return error_msg
    except Exception as e:
        error_msg = f"[ERROR] Unknown error editing file: {type(e).__name__}: {e}"
        logger.error(f"  [Tool: edit_file] {error_msg}")
        return error_msg
