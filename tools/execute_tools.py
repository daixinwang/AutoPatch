"""
tools/execute_tools.py
----------------------
安全的代码执行工具，供 TestRunner Agent 使用。

设计原则（安全沙箱）：
  1. 白名单机制：只允许执行预定义的安全命令（pytest / python / npm / cargo / go 等）
  2. 超时熔断：所有命令都有硬性超时限制，防止无限循环卡死 Agent
  3. 输出截断：stdout/stderr 超过阈值时自动截断，避免 LLM context 爆炸
  4. 进程隔离：使用 subprocess 子进程，失败不影响主进程
  5. 绝不崩溃：所有异常都捕获并以字符串形式返回给 LLM

工具列表：
  - run_pytest        : 对指定路径运行 pytest，返回测试报告
  - run_python_script : 运行单个 Python 脚本，捕获 stdout/stderr
  - run_test_command  : 运行各语言通用测试命令（npm/cargo/go/make 等）
  - verify_importable : 验证 Python 文件是否可正常 import（检测循环依赖和语法错误）
"""

import shlex
import subprocess
import sys
from pathlib import Path

from langchain_core.tools import tool

from tools.workspace import resolve_workspace_path, get_workspace

import logging

logger = logging.getLogger(__name__)

# ── 安全常量 ──────────────────────────────────
# 命令执行超时（秒）
DEFAULT_TIMEOUT_SECONDS: int = 30
MAX_TIMEOUT_SECONDS: int = 120

# 输出最大字节数（超出截断，防止撑爆 LLM 上下文）
MAX_OUTPUT_BYTES: int = 8_000

# 允许执行的命令白名单前缀（防止注入 rm -rf 等危险命令）
_SAFE_CMD_PREFIXES: tuple[str, ...] = (
    "pytest",
    "python",
    sys.executable,           # 当前 venv 的 python 路径
)


def _is_safe_command(cmd_args: list[str]) -> bool:
    """
    检查命令是否在白名单内。

    Args:
        cmd_args: 命令参数列表，如 ["pytest", "calc.py", "-v"]

    Returns:
        True 表示安全，False 表示不允许执行
    """
    if not cmd_args:
        return False
    first = cmd_args[0].lower()
    return any(first == prefix or first.endswith(f"/{prefix}") or first.endswith(f"\\{prefix}")
               for prefix in _SAFE_CMD_PREFIXES)


def _truncate_output(text: str, max_bytes: int = MAX_OUTPUT_BYTES) -> str:
    """
    截断过长的命令输出，保留头尾信息。

    Args:
        text:      原始输出字符串
        max_bytes: 最大保留字节数

    Returns:
        截断后的字符串（超长时标注截断位置）
    """
    encoded = text.encode("utf-8", errors="replace")
    if len(encoded) <= max_bytes:
        return text

    half = max_bytes // 2
    head = encoded[:half].decode("utf-8", errors="replace")
    tail = encoded[-half:].decode("utf-8", errors="replace")
    omitted = len(encoded) - max_bytes
    return f"{head}\n\n... [输出过长，中间 {omitted} 字节已省略] ...\n\n{tail}"


def _run_subprocess(
    cmd_args: list[str],
    cwd: str,
    timeout: int,
) -> dict:
    """
    执行子进程并收集结果（内部辅助函数，不是 LangChain tool）。

    Args:
        cmd_args: 命令及参数列表
        cwd:      工作目录
        timeout:  超时秒数

    Returns:
        包含 returncode / stdout / stderr / timed_out 的字典
    """
    try:
        result = subprocess.run(
            cmd_args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "timed_out": False,
        }
    except subprocess.TimeoutExpired as e:
        stdout = (e.stdout or b"").decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
        stderr = (e.stderr or b"").decode("utf-8", errors="replace") if isinstance(e.stderr, bytes) else (e.stderr or "")
        return {
            "returncode": -1,
            "stdout": stdout,
            "stderr": stderr,
            "timed_out": True,
        }


def _format_result(
    cmd_display: str,
    result: dict,
    cwd: str,
) -> str:
    """
    将子进程结果格式化为 LLM 友好的字符串报告。

    Args:
        cmd_display: 用于展示的命令字符串
        result:      _run_subprocess 的返回值
        cwd:         执行目录

    Returns:
        格式化的报告字符串
    """
    lines: list[str] = []
    lines.append(f"命令: {cmd_display}")
    lines.append(f"工作目录: {cwd}")

    if result["timed_out"]:
        lines.append(f"状态: ⏰ 超时（命令执行时间过长）")
    else:
        status = "✅ 成功 (exit 0)" if result["returncode"] == 0 else f"❌ 失败 (exit {result['returncode']})"
        lines.append(f"状态: {status}")

    if result["stdout"].strip():
        lines.append("\n--- stdout ---")
        lines.append(_truncate_output(result["stdout"]))

    if result["stderr"].strip():
        lines.append("\n--- stderr ---")
        lines.append(_truncate_output(result["stderr"]))

    if not result["stdout"].strip() and not result["stderr"].strip():
        lines.append("（无任何输出）")

    return "\n".join(lines)


# ──────────────────────────────────────────────
# 工具 1：运行 pytest
# ──────────────────────────────────────────────
@tool
def run_pytest(
    test_path: str = ".",
    extra_args: str = "-v --tb=short",
    working_directory: str = ".",
    timeout_seconds: int = 60,
) -> str:
    """
    对指定路径运行 pytest 测试套件，返回完整的测试报告（含通过/失败/错误详情）。

    适合场景：
      - 验证 Coder 修改的代码是否通过单元测试
      - 检查是否引入了回归 Bug
      - 查看具体的 AssertionError 和 traceback

    Args:
        test_path:          pytest 的测试目标，可以是目录、文件或 "模块::函数"
                            （默认 "." 表示自动发现当前目录下所有测试）。
        extra_args:         附加的 pytest 参数字符串，如 "-v --tb=short -x"
                            （-x 表示遇到第一个失败即停止）。
        working_directory:  执行 pytest 的工作目录（默认 "."）。
        timeout_seconds:    超时秒数，最大 {MAX_TIMEOUT_SECONDS} 秒（默认 60）。

    Returns:
        pytest 的完整输出报告（包含 stdout + stderr）；出错时返回错误描述。
    """
    logger.debug(f"  [Tool: run_pytest] 运行 pytest {test_path} {extra_args}")
    try:
        cwd = str(resolve_workspace_path(working_directory))
        timeout = max(1, min(timeout_seconds, MAX_TIMEOUT_SECONDS))

        # 构建命令：使用当前 venv 的 python -m pytest，确保包路径正确
        cmd_args = [sys.executable, "-m", "pytest", test_path]
        if extra_args.strip():
            cmd_args.extend(shlex.split(extra_args))

        result = _run_subprocess(cmd_args, cwd, timeout)
        report = _format_result(" ".join(cmd_args), result, cwd)

        status_emoji = "✅" if result["returncode"] == 0 else "❌"
        logger.debug(f"  [Tool: run_pytest] {status_emoji} 完成，exit code: {result['returncode']}")
        return report

    except Exception as e:
        error_msg = f"[错误] run_pytest 执行失败: {type(e).__name__}: {e}"
        logger.error(f"  [Tool: run_pytest] {error_msg}")
        return error_msg


# ──────────────────────────────────────────────
# 工具 2：运行单个 Python 脚本
# ──────────────────────────────────────────────
@tool
def run_python_script(
    script_path: str,
    script_args: str = "",
    working_directory: str = ".",
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """
    运行单个 Python 脚本文件，捕获并返回 stdout 和 stderr。

    适合场景：
      - 验证新创建的模块是否可以正常 import 和运行
      - 运行带有简单断言的冒烟测试脚本
      - 捕获脚本运行时的错误 traceback

    安全限制：
      - 只能执行 .py 文件
      - 超时自动终止（默认 {DEFAULT_TIMEOUT_SECONDS} 秒，最大 {MAX_TIMEOUT_SECONDS} 秒）
      - 输出超过 {MAX_OUTPUT_BYTES} 字节时自动截断

    Args:
        script_path:        要运行的 Python 脚本路径（.py 文件）。
        script_args:        传递给脚本的命令行参数字符串（可选）。
        working_directory:  执行脚本的工作目录（默认 "."）。
        timeout_seconds:    超时秒数（默认 {DEFAULT_TIMEOUT_SECONDS}，最大 {MAX_TIMEOUT_SECONDS}）。

    Returns:
        脚本运行的完整输出报告（stdout + stderr + exit code）；出错返回错误描述。
    """
    logger.debug(f"  [Tool: run_python_script] 运行脚本: {script_path}")
    try:
        script = resolve_workspace_path(script_path)

        # 安全检查：只允许 .py 文件
        if script.suffix.lower() != ".py":
            return f"[错误] 安全限制：只允许运行 .py 文件，拒绝执行: {script_path}"

        if not script.exists():
            return f"[错误] 脚本文件不存在: {script_path}"

        cwd = str(resolve_workspace_path(working_directory))
        timeout = max(1, min(timeout_seconds, MAX_TIMEOUT_SECONDS))

        cmd_args = [sys.executable, str(script.resolve())]
        if script_args.strip():
            cmd_args.extend(shlex.split(script_args))

        result = _run_subprocess(cmd_args, cwd, timeout)
        report = _format_result(" ".join(cmd_args), result, cwd)

        status_emoji = "✅" if result["returncode"] == 0 else "❌"
        logger.debug(f"  [Tool: run_python_script] {status_emoji} 完成，exit code: {result['returncode']}")
        return report

    except Exception as e:
        error_msg = f"[错误] run_python_script 执行失败: {type(e).__name__}: {e}"
        logger.error(f"  [Tool: run_python_script] {error_msg}")
        return error_msg


# ──────────────────────────────────────────────
# 工具 3：多语言通用测试命令
# ──────────────────────────────────────────────

# 允许执行的测试命令白名单（防止注入危险命令）
_SAFE_TEST_COMMANDS: dict[str, list[str]] = {
    # Node.js / JavaScript / TypeScript
    "npm test":         ["npm", "test"],
    "npm run test":     ["npm", "run", "test"],
    "yarn test":        ["yarn", "test"],
    "pnpm test":        ["pnpm", "test"],
    # Rust
    "cargo test":       ["cargo", "test"],
    # Go
    "go test ./...":    ["go", "test", "./..."],
    "go test .":        ["go", "test", "."],
    # Java / Kotlin
    "mvn test":         ["mvn", "test"],
    "gradle test":      ["gradle", "test"],
    "./gradlew test":   ["./gradlew", "test"],
    # Generic
    "make test":        ["make", "test"],
}


@tool
def run_test_command(
    command: str,
    working_directory: str = ".",
    timeout_seconds: int = 120,
) -> str:
    """
    对非 Python 项目运行语言原生测试命令（npm test / cargo test / go test 等）。

    仅允许执行预定义白名单中的命令，拒绝任意 shell 命令以防注入。

    支持的命令（完整列表）：
      npm test, npm run test, yarn test, pnpm test
      cargo test
      go test ./..., go test .
      mvn test, gradle test, ./gradlew test
      make test

    Args:
        command:           要执行的测试命令（必须完整匹配白名单中的某一项）。
        working_directory: 执行命令的工作目录（默认 "." 即仓库根目录）。
        timeout_seconds:   超时秒数（默认 120，最大 {MAX_TIMEOUT_SECONDS} 秒）。

    Returns:
        命令的完整输出报告（stdout + stderr + exit code）；出错返回错误描述。
    """
    logger.debug(f"  [Tool: run_test_command] 执行: {command!r}")
    try:
        normalized = command.strip().lower()
        cmd_args = _SAFE_TEST_COMMANDS.get(normalized)
        if cmd_args is None:
            allowed = "\n  ".join(_SAFE_TEST_COMMANDS.keys())
            return (
                f"[错误] 命令不在白名单中: {command!r}\n"
                f"允许的命令：\n  {allowed}"
            )

        cwd = str(resolve_workspace_path(working_directory))
        timeout = max(1, min(timeout_seconds, MAX_TIMEOUT_SECONDS))

        result = _run_subprocess(cmd_args, cwd, timeout)
        report = _format_result(command, result, cwd)

        status_emoji = "✅" if result["returncode"] == 0 else "❌"
        logger.debug(f"  [Tool: run_test_command] {status_emoji} 完成，exit code: {result['returncode']}")
        return report

    except Exception as e:
        error_msg = f"[错误] run_test_command 执行失败: {type(e).__name__}: {e}"
        logger.error(f"  [Tool: run_test_command] {error_msg}")
        return error_msg


# ──────────────────────────────────────────────
# 工具 4：验证 Python 模块是否可正常 import
# ──────────────────────────────────────────────
@tool
def verify_importable(file_path: str) -> str:
    """
    验证修改后的 Python 源文件是否可以正常 import（检测语法错误和循环依赖）。

    在修改任何 Python 源文件后调用此工具，确保没有破坏模块的可导入性。

    Args:
        file_path: 要验证的 Python 文件路径（相对于工作目录，如 "sympy/printing/ccode.py"）

    Returns:
        成功时返回 "[成功] 模块可正常导入：<module_name>"；
        失败时返回包含完整错误信息的字符串。
    """
    logger.debug(f"  [Tool: verify_importable] 验证文件: {file_path}")
    try:
        path = resolve_workspace_path(file_path)

        if not path.exists():
            return f"[错误] 文件不存在: {file_path}"
        if path.suffix.lower() != ".py":
            return f"[错误] 只支持 .py 文件，收到: {file_path}"

        # 将相对路径转换为模块名
        # 例：sympy/printing/ccode.py → sympy.printing.ccode
        rel = Path(file_path).as_posix().removesuffix(".py")
        module_name = rel.replace("/", ".")

        cwd = get_workspace()
        # 安全说明：命令固定为 [sys.executable, "-c", "import <module>"]，
        # module_name 由文件路径机械转换而来（不含用户自由输入），无需 _is_safe_command 白名单校验。
        result = _run_subprocess(
            [sys.executable, "-c", f"import {module_name}"],
            cwd=cwd,
            timeout=15,
        )

        if result["timed_out"]:
            return (
                f"[超时] import {module_name} 超时（15s），"
                "可能存在循环导入，请检查模块级 import 语句"
            )

        if result["returncode"] == 0:
            logger.info(f"  [Tool: verify_importable] ✅ 可正常导入: {module_name}")
            return f"[成功] 模块可正常导入：{module_name}"

        error_output = _truncate_output(result["stderr"] or result["stdout"])
        logger.warning(f"  [Tool: verify_importable] ❌ 导入失败: {module_name}")
        return (
            f"[失败] import {module_name} 出错，请修复后重试：\n{error_output}"
        )

    except Exception as e:
        error_msg = f"[错误] verify_importable 执行失败: {type(e).__name__}: {e}"
        logger.error(f"  [Tool: verify_importable] {error_msg}")
        return error_msg
