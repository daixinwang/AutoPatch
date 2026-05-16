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

import os
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
    return f"{head}\n\n... [output too long, {omitted} bytes omitted from middle] ...\n\n{tail}"


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
    lines.append(f"Command: {cmd_display}")
    lines.append(f"Working dir: {cwd}")

    if result["timed_out"]:
        lines.append("Status: ⏰ TIMEOUT (command took too long)")
    else:
        status = "✅ SUCCESS (exit 0)" if result["returncode"] == 0 else f"❌ FAILED (exit {result['returncode']})"
        lines.append(f"Status: {status}")

    if result["stdout"].strip():
        lines.append("\n--- stdout ---")
        lines.append(_truncate_output(result["stdout"]))

    if result["stderr"].strip():
        lines.append("\n--- stderr ---")
        lines.append(_truncate_output(result["stderr"]))

    if not result["stdout"].strip() and not result["stderr"].strip():
        lines.append("(no output)")

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
    Run pytest on the given path and return the full test report (including pass/fail/error details).

    Useful for:
      - Verifying that the Coder's changes pass unit tests
      - Checking for regressions
      - Viewing specific AssertionErrors and tracebacks

    Args:
        test_path:          pytest target: directory, file, or "module::function"
                            (default "." auto-discovers all tests in the current directory).
        extra_args:         Additional pytest flags, e.g. "-v --tb=short -x"
                            (-x stops on first failure).
        working_directory:  Working directory for pytest (default ".").
        timeout_seconds:    Timeout in seconds, max {MAX_TIMEOUT_SECONDS} (default 60).

    Returns:
        Full pytest output report (stdout + stderr); error description on failure.
    """
    logger.debug(f"  [Tool: run_pytest] running pytest {test_path} {extra_args}")
    try:
        cwd = str(resolve_workspace_path(working_directory))
        timeout = max(1, min(timeout_seconds, MAX_TIMEOUT_SECONDS))

        cmd_args = [sys.executable, "-m", "pytest", test_path]
        if extra_args.strip():
            cmd_args.extend(shlex.split(extra_args))

        result = _run_subprocess(cmd_args, cwd, timeout)
        report = _format_result(" ".join(cmd_args), result, cwd)

        status_emoji = "✅" if result["returncode"] == 0 else "❌"
        logger.debug(f"  [Tool: run_pytest] {status_emoji} done, exit code: {result['returncode']}")
        return report

    except Exception as e:
        error_msg = f"[ERROR] run_pytest failed: {type(e).__name__}: {e}"
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
    Run a single Python script file and capture stdout and stderr.

    Useful for:
      - Verifying that a newly created module can be imported and run
      - Running a smoke test script with simple assertions
      - Capturing runtime error tracebacks

    Safety limits:
      - Only .py files are allowed
      - Auto-terminates on timeout (default {DEFAULT_TIMEOUT_SECONDS}s, max {MAX_TIMEOUT_SECONDS}s)
      - Output truncated if it exceeds {MAX_OUTPUT_BYTES} bytes

    Args:
        script_path:        Path to the Python script (.py file).
        script_args:        Command-line arguments to pass to the script (optional).
        working_directory:  Working directory for the script (default ".").
        timeout_seconds:    Timeout in seconds (default {DEFAULT_TIMEOUT_SECONDS}, max {MAX_TIMEOUT_SECONDS}).

    Returns:
        Full output report (stdout + stderr + exit code); error description on failure.
    """
    logger.debug(f"  [Tool: run_python_script] running script: {script_path}")
    try:
        script = resolve_workspace_path(script_path)

        if script.suffix.lower() != ".py":
            return f"[ERROR] Safety restriction: only .py files are allowed, refused: {script_path}"

        if not script.exists():
            return f"[ERROR] Script file not found: {script_path}"

        cwd = str(resolve_workspace_path(working_directory))
        timeout = max(1, min(timeout_seconds, MAX_TIMEOUT_SECONDS))

        cmd_args = [sys.executable, str(script.resolve())]
        if script_args.strip():
            cmd_args.extend(shlex.split(script_args))

        result = _run_subprocess(cmd_args, cwd, timeout)
        report = _format_result(" ".join(cmd_args), result, cwd)

        status_emoji = "✅" if result["returncode"] == 0 else "❌"
        logger.debug(f"  [Tool: run_python_script] {status_emoji} done, exit code: {result['returncode']}")
        return report

    except Exception as e:
        error_msg = f"[ERROR] run_python_script failed: {type(e).__name__}: {e}"
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
    Run a language-native test command for non-Python projects (npm test / cargo test / go test, etc.).

    Only commands from a predefined whitelist are allowed; arbitrary shell commands are rejected to prevent injection.

    Supported commands (full list):
      npm test, npm run test, yarn test, pnpm test
      cargo test
      go test ./..., go test .
      mvn test, gradle test, ./gradlew test
      make test

    Args:
        command:           Test command to run (must exactly match one of the whitelist entries).
        working_directory: Working directory (default "." = repository root).
        timeout_seconds:   Timeout in seconds (default 120, max {MAX_TIMEOUT_SECONDS}).

    Returns:
        Full output report (stdout + stderr + exit code); error description on failure.
    """
    logger.debug(f"  [Tool: run_test_command] executing: {command!r}")
    try:
        normalized = command.strip().lower()
        cmd_args = _SAFE_TEST_COMMANDS.get(normalized)
        if cmd_args is None:
            allowed = "\n  ".join(_SAFE_TEST_COMMANDS.keys())
            return (
                f"[ERROR] Command not in whitelist: {command!r}\n"
                f"Allowed commands:\n  {allowed}"
            )

        cwd = str(resolve_workspace_path(working_directory))
        timeout = max(1, min(timeout_seconds, MAX_TIMEOUT_SECONDS))

        result = _run_subprocess(cmd_args, cwd, timeout)
        report = _format_result(command, result, cwd)

        status_emoji = "✅" if result["returncode"] == 0 else "❌"
        logger.debug(f"  [Tool: run_test_command] {status_emoji} done, exit code: {result['returncode']}")
        return report

    except Exception as e:
        error_msg = f"[ERROR] run_test_command failed: {type(e).__name__}: {e}"
        logger.error(f"  [Tool: run_test_command] {error_msg}")
        return error_msg


# ──────────────────────────────────────────────
# 工具 4：验证 Python 模块是否可正常 import
# ──────────────────────────────────────────────
@tool
def verify_importable(file_path: str) -> str:
    """
    Verify that a modified Python source file can be imported cleanly (detects syntax errors and circular imports).

    Call this after modifying any Python source file to ensure the module's importability is not broken.

    Args:
        file_path: Path to the Python file to verify (relative to workspace, e.g. "sympy/printing/ccode.py")

    Returns:
        "[OK] Module imports successfully: <module_name>" on success;
        a string containing the full error on failure.
    """
    logger.debug(f"  [Tool: verify_importable] verifying file: {file_path}")
    if os.getenv("AUTOPATCH_DOCKER_EVAL"):
        logger.info(f"  [Tool: verify_importable] Docker eval mode, skipping local import check: {file_path}")
        return "[SKIPPED] Local import verification is disabled in Docker eval mode. Rely on TestRunner results instead."
    try:
        path = resolve_workspace_path(file_path)

        if not path.exists():
            return f"[ERROR] File not found: {file_path}"
        if path.suffix.lower() != ".py":
            return f"[ERROR] Only .py files are supported, got: {file_path}"

        workspace = Path(get_workspace())
        if file_path.startswith("src/") and (workspace / "src").exists():
            rel = Path(file_path[4:]).as_posix().removesuffix(".py")
            cwd = str(workspace / "src")
        else:
            rel = Path(file_path).as_posix().removesuffix(".py")
            cwd = get_workspace()
        module_name = rel.replace("/", ".")

        result = _run_subprocess(
            [sys.executable, "-c", f"import {module_name}"],
            cwd=cwd,
            timeout=15,
        )

        if result["timed_out"]:
            return (
                f"[TIMEOUT] import {module_name} timed out (15s). "
                "Possible circular import — check module-level import statements."
            )

        if result["returncode"] == 0:
            logger.info(f"  [Tool: verify_importable] ✅ import OK: {module_name}")
            return f"[OK] Module imports successfully: {module_name}"

        error_output = _truncate_output(result["stderr"] or result["stdout"])
        logger.warning(f"  [Tool: verify_importable] ❌ import failed: {module_name}")
        return (
            f"[FAILED] import {module_name} errored — fix and retry:\n{error_output}"
        )

    except Exception as e:
        error_msg = f"[ERROR] verify_importable failed: {type(e).__name__}: {e}"
        logger.error(f"  [Tool: verify_importable] {error_msg}")
        return error_msg
