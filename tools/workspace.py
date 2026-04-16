"""
tools/workspace.py
------------------
线程安全的工作目录管理。

使用 contextvars.ContextVar 代替全局 os.chdir，确保并发请求互不干扰：
每个 asyncio Task（以及通过 copy_context() 启动的线程）都有自己独立
的"当前工作目录"，对其他请求完全透明。

用法（server.py / autopatch.py 中设置）：
    from tools.workspace import set_workspace, reset_workspace

    token = set_workspace("/path/to/cloned/repo")
    try:
        # 运行 Agent...
    finally:
        reset_workspace(token)

工具内部解析路径：
    from tools.workspace import resolve_workspace_path
    path = resolve_workspace_path("calc.py")  # → /tmp/autopatch_xxx/calc.py
"""

from contextvars import ContextVar, Token
from pathlib import Path

# 每个异步任务/线程独立的工作目录，默认值为进程启动时的 CWD
_workspace_dir: ContextVar[str] = ContextVar("workspace_dir", default=".")


def set_workspace(path: str) -> Token:
    """
    设置当前上下文的工作目录，返回 Token 供还原使用。

    此操作只影响当前 asyncio Task 或线程上下文，不修改全局 os.getcwd()。

    Args:
        path: 工作目录的绝对路径（相对路径会先转为绝对路径）

    Returns:
        Token，传给 reset_workspace() 可还原到设置前的值
    """
    return _workspace_dir.set(str(Path(path).resolve()))


def reset_workspace(token: Token) -> None:
    """
    还原工作目录到 set_workspace() 调用之前的值。

    Args:
        token: set_workspace() 返回的 Token
    """
    _workspace_dir.reset(token)


def get_workspace() -> str:
    """返回当前上下文的工作目录路径字符串。"""
    return _workspace_dir.get()


def resolve_workspace_path(path_str: str) -> Path:
    """
    将路径字符串解析为绝对 Path 对象，并强制限定在 workspace 内。

    - 拒绝绝对路径输入（防止访问 /etc/passwd 等系统文件）
    - 相对路径拼接到当前工作目录后，resolve() 去除 .. 再校验包含关系

    Args:
        path_str: 文件或目录路径（仅接受相对路径）

    Returns:
        解析后的绝对 Path 对象

    Raises:
        ValueError: 路径逃逸出 workspace 范围时
    """
    p = Path(path_str)
    workspace_root = Path(get_workspace()).resolve()

    if p.is_absolute():
        resolved = p.resolve()
    else:
        resolved = (workspace_root / p).resolve()

    if not resolved.is_relative_to(workspace_root):
        raise ValueError(
            f"路径安全限制：{path_str!r} 解析后逃逸出工作目录 {workspace_root}"
        )
    return resolved
