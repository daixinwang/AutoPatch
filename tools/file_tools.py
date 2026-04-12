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


# ──────────────────────────────────────────────
# 工具 1：读取文件
# ──────────────────────────────────────────────
@tool
def read_file(file_path: str) -> str:
    """
    读取指定路径文件的内容并以字符串形式返回。

    Args:
        file_path: 要读取的文件路径（支持相对路径和绝对路径）。

    Returns:
        文件内容字符串；若文件不存在或读取失败，返回描述错误的字符串。
    """
    print(f"  [Tool: read_file] 尝试读取文件: {file_path}")
    try:
        path = resolve_workspace_path(file_path)
        if not path.exists():
            error_msg = f"[错误] 文件不存在: {file_path}"
            print(f"  [Tool: read_file] {error_msg}")
            return error_msg

        if not path.is_file():
            error_msg = f"[错误] 路径存在但不是一个文件: {file_path}"
            print(f"  [Tool: read_file] {error_msg}")
            return error_msg

        content = path.read_text(encoding="utf-8")
        print(f"  [Tool: read_file] 成功读取，内容长度: {len(content)} 字符")
        return content

    except PermissionError:
        error_msg = f"[错误] 没有权限读取文件: {file_path}"
        print(f"  [Tool: read_file] {error_msg}")
        return error_msg
    except Exception as e:
        error_msg = f"[错误] 读取文件时发生未知错误: {type(e).__name__}: {e}"
        print(f"  [Tool: read_file] {error_msg}")
        return error_msg


# ──────────────────────────────────────────────
# 工具 2：覆盖写入 / 创建文件
# ──────────────────────────────────────────────
@tool
def write_and_replace_file(file_path: str, content: str) -> str:
    """
    将 content 写入指定路径的文件。若文件已存在则覆盖，若不存在则创建（包括中间目录）。

    Args:
        file_path: 目标文件路径（支持相对路径和绝对路径）。
        content:   要写入的完整文件内容字符串。

    Returns:
        写入成功的确认信息；若写入失败，返回描述错误的字符串。
    """
    print(f"  [Tool: write_and_replace_file] 尝试写入文件: {file_path}")
    try:
        path = resolve_workspace_path(file_path)

        # 自动创建不存在的父目录
        path.parent.mkdir(parents=True, exist_ok=True)

        path.write_text(content, encoding="utf-8")

        # 写入后校验
        written_size = path.stat().st_size
        print(f"  [Tool: write_and_replace_file] 写入成功，文件大小: {written_size} bytes")
        return f"[成功] 文件已写入: {file_path}（{written_size} bytes）"

    except PermissionError:
        error_msg = f"[错误] 没有权限写入文件: {file_path}"
        print(f"  [Tool: write_and_replace_file] {error_msg}")
        return error_msg
    except OSError as e:
        error_msg = f"[错误] 文件系统错误: {type(e).__name__}: {e}"
        print(f"  [Tool: write_and_replace_file] {error_msg}")
        return error_msg
    except Exception as e:
        error_msg = f"[错误] 写入文件时发生未知错误: {type(e).__name__}: {e}"
        print(f"  [Tool: write_and_replace_file] {error_msg}")
        return error_msg


# ──────────────────────────────────────────────
# 工具 3：精确编辑文件（局部替换）
# ──────────────────────────────────────────────
@tool
def edit_file(file_path: str, old_string: str, new_string: str) -> str:
    """
    对已有文件进行精确的局部文本替换。仅替换第一处匹配。

    这是修改现有文件的首选工具——只需提供要替换的原始片段和新片段，
    无需输出整个文件内容，适用于任意大小的文件。

    Args:
        file_path:   要编辑的文件路径（支持相对路径和绝对路径）。
        old_string:  文件中要被替换的原始文本（必须与文件中的内容完全匹配，包括缩进和空白）。
        new_string:  用于替换的新文本。

    Returns:
        编辑成功的确认信息；若失败，返回描述错误的字符串。
    """
    print(f"  [Tool: edit_file] 编辑文件: {file_path}")
    try:
        path = resolve_workspace_path(file_path)

        if not path.exists():
            error_msg = f"[错误] 文件不存在: {file_path}"
            print(f"  [Tool: edit_file] {error_msg}")
            return error_msg

        if not path.is_file():
            error_msg = f"[错误] 路径不是文件: {file_path}"
            print(f"  [Tool: edit_file] {error_msg}")
            return error_msg

        content = path.read_text(encoding="utf-8")

        if old_string == new_string:
            return "[提示] old_string 和 new_string 相同，未做修改。"

        if old_string not in content:
            # 提供上下文帮助 LLM 调试
            preview = content[:500] + "..." if len(content) > 500 else content
            error_msg = (
                f"[错误] 在文件 {file_path} 中未找到要替换的文本。\n"
                f"请确保 old_string 与文件内容完全匹配（包括缩进、空行和空白字符）。\n"
                f"文件前 500 字符预览:\n{preview}"
            )
            print(f"  [Tool: edit_file] old_string 未匹配")
            return error_msg

        count = content.count(old_string)
        if count > 1:
            error_msg = (
                f"[警告] old_string 在文件中出现 {count} 次，"
                f"为安全起见仅替换第一处。如需全部替换请分次操作或提供更长的上下文。"
            )
            print(f"  [Tool: edit_file] {error_msg}")

        new_content = content.replace(old_string, new_string, 1)
        path.write_text(new_content, encoding="utf-8")

        written_size = path.stat().st_size
        print(f"  [Tool: edit_file] 编辑成功，文件大小: {written_size} bytes")
        return f"[成功] 文件已编辑: {file_path}（{written_size} bytes）"

    except PermissionError:
        error_msg = f"[错误] 没有权限编辑文件: {file_path}"
        print(f"  [Tool: edit_file] {error_msg}")
        return error_msg
    except Exception as e:
        error_msg = f"[错误] 编辑文件时发生未知错误: {type(e).__name__}: {e}"
        print(f"  [Tool: edit_file] {error_msg}")
        return error_msg
