"""
eval/verify.py
--------------
测试执行与结果判定。
通过 subprocess 直接运行测试（不经过 Agent 的 TestRunner）。
"""

from __future__ import annotations

import logging
import re
import subprocess
from typing import Callable, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

def _build_django_cmd(test_ids: List[str], workspace: str) -> List[str]:
    """Django 的测试命令。test_ids 形如 'tests.test_module.TestClass.test_method'。"""
    return ["python", "-m", "django", "test", "--settings=tests.test_sqlite", "--parallel=1"] + test_ids


def _build_pytest_cmd(test_ids: List[str], workspace: str) -> List[str]:
    """默认 pytest 命令。"""
    return ["python", "-m", "pytest", "-xvs"] + test_ids


# ── Repo 特定 test runner ──

REPO_TEST_RUNNERS: Dict[str, Dict] = {
    "django/django": {
        "build_cmd": _build_django_cmd,
    },
}


def run_tests(
    test_ids: List[str],
    workspace_path: str,
    repo: str = "",
    timeout: int = 300,
) -> Dict[str, bool]:
    """
    运行指定测试并返回 per-test pass/fail。

    Args:
        test_ids: 测试标识列表
        workspace_path: 工作目录
        repo: 仓库名（用于选择 test runner）
        timeout: 超时秒数

    Returns:
        {test_id: True/False} 字典
    """
    if not test_ids:
        return {}

    runner_cfg = REPO_TEST_RUNNERS.get(repo, {})
    build_cmd: Callable = runner_cfg.get("build_cmd", _build_pytest_cmd)
    cmd = build_cmd(test_ids, workspace_path)

    try:
        result = subprocess.run(
            cmd,
            cwd=workspace_path,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + "\n" + result.stderr
    except subprocess.TimeoutExpired:
        return {tid: False for tid in test_ids}

    # 先尝试 pytest 格式解析
    parsed = _parse_pytest_output(output, test_ids)
    if parsed:
        return parsed

    # 再尝试 Django 格式
    parsed = _parse_django_output(output, test_ids)
    if parsed:
        return parsed

    # 最后回退：如果 returncode == 0 全部算 pass，否则全 fail
    all_pass = result.returncode == 0
    return {tid: all_pass for tid in test_ids}


def classify_result(
    fail_to_pass: Dict[str, bool],
    pass_to_pass: Dict[str, bool],
) -> str:
    """
    分类评测结果:
      - "resolved":            所有 FAIL_TO_PASS 通过 + 所有 PASS_TO_PASS 通过
      - "partially_resolved":  部分 FAIL_TO_PASS 通过（或有 PASS_TO_PASS 回退）
      - "failed":              无 FAIL_TO_PASS 通过
    """
    f2p_passed = sum(1 for v in fail_to_pass.values() if v)
    f2p_total = len(fail_to_pass)
    p2p_passed = sum(1 for v in pass_to_pass.values() if v)
    p2p_total = len(pass_to_pass)

    if f2p_total == 0:
        return "failed"

    if f2p_passed == f2p_total and p2p_passed == p2p_total:
        return "resolved"

    if f2p_passed > 0:
        return "partially_resolved"

    return "failed"


# ── 输出解析器 ──

def _parse_pytest_output(output: str, test_ids: List[str]) -> Optional[Dict[str, bool]]:
    """解析 pytest -v 输出，提取 PASSED/FAILED/ERROR 状态。"""
    results: Dict[str, bool] = {}

    # pytest -v 格式: "tests/test_foo.py::TestBar::test_baz PASSED"
    pattern = re.compile(r"(\S+::\S+)\s+(PASSED|FAILED|ERROR|XFAIL|XPASS|SKIPPED)")
    found = {}
    for m in pattern.finditer(output):
        node_id, status = m.group(1), m.group(2)
        found[node_id] = status in ("PASSED", "XPASS")

    if not found:
        return None

    # 将 test_ids 映射到 pytest node ids
    for tid in test_ids:
        if tid in found:
            results[tid] = found[tid]
        else:
            # 尝试模糊匹配（test_id 可能是 node_id 的子串）
            matched = False
            for node_id, passed in found.items():
                if tid in node_id or node_id.endswith(tid):
                    results[tid] = passed
                    matched = True
                    break
            if not matched:
                results[tid] = False  # 未找到 → 假定失败

    return results


def _parse_django_output(output: str, test_ids: List[str]) -> Optional[Dict[str, bool]]:
    """解析 Django test runner 输出。"""
    # Django 输出示例:
    # "test_method (tests.test_module.TestClass) ... ok"
    # "test_method (tests.test_module.TestClass) ... FAIL"
    pattern = re.compile(r"(\w+)\s+\(([^)]+)\)\s*\.\.\.\s*(ok|FAIL|ERROR|skipped)")
    found = {}
    for m in pattern.finditer(output):
        method, path, status = m.group(1), m.group(2), m.group(3)
        full_id = f"{path}.{method}"
        found[full_id] = status == "ok"

    if not found:
        # 也检查 "Ran X tests" + OK/FAILED
        if "OK" in output and re.search(r"Ran \d+ tests?", output):
            return {tid: True for tid in test_ids}
        if "FAILED" in output:
            return {tid: False for tid in test_ids}
        return None

    results: Dict[str, bool] = {}
    for tid in test_ids:
        if tid in found:
            results[tid] = found[tid]
        else:
            matched = False
            for full_id, passed in found.items():
                if tid in full_id or full_id.endswith(tid):
                    results[tid] = passed
                    matched = True
                    break
            if not matched:
                results[tid] = False

    return results


def run_tests_docker(
    test_ids: List[str],
    container_name: str,
    workspace: str,
    repo: str = "",
    timeout: int = 300,
    container_path: str = "/testbed",
) -> Dict[str, bool]:
    """
    在 Docker 容器中运行测试。

    流程：
      1. docker cp <workspace>/. <container>:<container_path>/  — 同步本地改动到容器
      2. docker exec <container> bash -c "cd <container_path> && pytest ..."
      3. 复用现有 _parse_pytest_output / _parse_django_output 解析结果

    Args:
        test_ids:       测试标识列表
        container_name: Docker 容器名（如 "autopatch_pallets__flask-4045"）
        workspace:      本地工作目录路径（改动已在此处）
        repo:           仓库名（用于选择 test runner，默认 pytest）
        timeout:        超时秒数
        container_path: 容器内 repo 路径（默认 "/testbed"，部分 instance 用 "/repo"）

    Returns:
        {test_id: True/False} 字典
    """
    if not test_ids:
        return {}

    # 1. 将本地改动同步回容器
    sync_result = subprocess.run(
        ["docker", "cp", f"{container_name}:{container_path}/", f"{workspace}/."],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if sync_result.returncode != 0:
        logger.error(
            "  [DockerVerify] docker cp failed (exit %d): %s",
            sync_result.returncode,
            sync_result.stderr[:200],
        )
        return {tid: False for tid in test_ids}

    # 2. 构建测试命令
    runner_cfg = REPO_TEST_RUNNERS.get(repo, {})
    build_cmd = runner_cfg.get("build_cmd", _build_pytest_cmd)
    test_cmd_parts = build_cmd(test_ids, workspace)
    inner_cmd = f"cd {container_path} && " + " ".join(test_cmd_parts)

    # 3. 在容器内运行测试
    try:
        result = subprocess.run(
            ["docker", "exec", container_name, "bash", "-c", inner_cmd],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + "\n" + result.stderr
    except subprocess.TimeoutExpired:
        return {tid: False for tid in test_ids}

    # 4. 解析输出（复用现有解析器）
    parsed = _parse_pytest_output(output, test_ids)
    if parsed:
        return parsed

    parsed = _parse_django_output(output, test_ids)
    if parsed:
        return parsed

    all_pass = result.returncode == 0
    return {tid: all_pass for tid in test_ids}
