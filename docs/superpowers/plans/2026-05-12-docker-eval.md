# Docker-Based SWE-bench Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 eval 框架支持通过 SWE-bench 官方 Docker 镜像搭建精确的测试环境，消除 `pip install` 的依赖版本冲突问题。

**Architecture:** 新建 `eval/docker_env.py` 提供 `DockerEnvironment` 类（接口与现有 `InstanceEnvironment` 一致）；在 `eval/verify.py` 新增 `run_tests_docker()` 函数；`eval/evaluator.py` 按 `config.use_docker` 在运行时选择环境和测试执行器；`eval/config.py` + `run_eval.py` 新增相应配置和 CLI 参数。Agent pipeline 代码零改动。

**Tech Stack:** Python, subprocess, Docker CLI, pytest, unittest.mock

---

## 文件改动一览

| 文件 | 操作 | 职责 |
|---|---|---|
| `eval/config.py` | 修改 | 新增 `use_docker`、`docker_image_prefix`、`keep_image` 字段和 CLI 参数 |
| `eval/docker_env.py` | 新建 | `DockerEnvironment` 类：pull + run + cp + patch + cleanup |
| `eval/verify.py` | 修改 | 新增 `run_tests_docker()` |
| `eval/evaluator.py` | 修改 | 按 `use_docker` 选择 env 类型和测试执行函数 |
| `run_eval.py` | 修改 | 新增 `--docker` / `--keep-image` CLI 参数 |
| `tests/test_docker_env.py` | 新建 | DockerEnvironment 单元测试（mock subprocess） |
| `tests/test_docker_verify.py` | 新建 | run_tests_docker 单元测试（mock subprocess） |

---

## Task 1：Config 和 CLI 参数

**Files:**
- Modify: `eval/config.py`
- Modify: `run_eval.py`

- [ ] **Step 1：在 `eval/config.py` 新增三个 Docker 字段**

在 `EvalConfig` dataclass 的 `# ── 续跑 ──` 区块之后，新增 `# ── Docker ──` 区块：

```python
    # ── Docker ──
    use_docker: bool = False
    docker_image_prefix: str = "swebench/sweb.eval.x86_64"
    keep_image: bool = False
```

- [ ] **Step 2：在 `from_cli` 中新增对应的 argparse 参数**

在 `p.add_argument("--no-resume", ...)` 之后追加：

```python
        p.add_argument("--docker", action="store_true", default=False)
        p.add_argument("--keep-image", action="store_true", default=False)
        p.add_argument(
            "--docker-image-prefix",
            default="swebench/sweb.eval.x86_64",
            dest="docker_image_prefix",
        )
```

- [ ] **Step 3：在 `from_cli` 的 `return cls(...)` 中传入新字段**

在现有的最后一行 `resume=not args.no_resume,` 之后追加：

```python
            use_docker=args.docker,
            docker_image_prefix=args.docker_image_prefix,
            keep_image=args.keep_image,
```

- [ ] **Step 4：验证 CLI 参数正确注册**

```bash
source .venv/bin/activate
python run_eval.py --help | grep -E "docker|keep-image"
```

期望输出包含：`--docker`、`--keep-image`、`--docker-image-prefix`

- [ ] **Step 5：提交**

```bash
git add eval/config.py
git commit -m "feat: add Docker config fields to EvalConfig"
```

---

## Task 2：DockerEnvironment 类

**Files:**
- Create: `eval/docker_env.py`
- Create: `tests/test_docker_env.py`

- [ ] **Step 1：写失败测试（只测纯逻辑，不调用真实 Docker）**

新建 `tests/test_docker_env.py`：

```python
"""
tests/test_docker_env.py
------------------------
Unit tests for eval/docker_env.py (pure logic only, no real Docker).
"""
from dataclasses import dataclass
from eval.docker_env import DockerEnvironment


@dataclass
class _FakeInstance:
    instance_id: str = "pallets__flask-4045"
    repo: str = "pallets/flask"
    test_patch: str = ""
    fail_to_pass: list = None
    pass_to_pass: list = None

    def __post_init__(self):
        if self.fail_to_pass is None:
            self.fail_to_pass = []
        if self.pass_to_pass is None:
            self.pass_to_pass = []


@dataclass
class _FakeConfig:
    docker_image_prefix: str = "swebench/sweb.eval.x86_64"
    keep_image: bool = False
    workdir_base: str = "/tmp/autopatch_test"


class TestDockerEnvironmentProperties:
    def _make_env(self, instance_id="pallets__flask-4045"):
        inst = _FakeInstance(instance_id=instance_id)
        cfg = _FakeConfig()
        return DockerEnvironment(inst, cfg)

    def test_image_name_default_prefix(self):
        env = self._make_env()
        assert env.image_name == "swebench/sweb.eval.x86_64.pallets__flask-4045:latest"

    def test_image_name_custom_prefix(self):
        inst = _FakeInstance()
        cfg = _FakeConfig(docker_image_prefix="myrepo/images")
        env = DockerEnvironment(inst, cfg)
        assert env.image_name == "myrepo/images.pallets__flask-4045:latest"

    def test_container_name(self):
        env = self._make_env()
        assert env.container_name == "autopatch_pallets__flask-4045"

    def test_container_name_with_underscores(self):
        env = self._make_env("sympy__sympy-20154")
        assert env.container_name == "autopatch_sympy__sympy-20154"
```

- [ ] **Step 2：运行测试，确认失败**

```bash
pytest tests/test_docker_env.py -v
```

期望：`ImportError: No module named 'eval.docker_env'`

- [ ] **Step 3：创建 `eval/docker_env.py`**

```python
"""
eval/docker_env.py
------------------
Docker-based environment for SWE-bench evaluation.

Per-instance workflow:
  docker pull <image>
  docker run -d --name <container> <image> sleep infinity
  docker cp <container>:/testbed → <local_workspace>  (fallback: /repo)
  git apply test_patch locally
  [Agent runs against local workspace]
  [Tests run via docker exec after syncing local changes back]
  docker stop + rm + optionally rmi
  rm -rf <local_workspace>
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Optional, Set

import logging

from eval.config import EvalConfig
from eval.dataset import SWEBenchInstance
from eval.instance_env import SetupError

logger = logging.getLogger(__name__)

# Paths inside the Docker container where the repo may live
_CONTAINER_REPO_PATHS = ["/testbed", "/repo"]


class DockerSetupError(SetupError):
    """Docker environment setup failed."""


class DockerEnvironment:
    """Manages a Docker-based workspace for a single SWE-bench instance."""

    def __init__(self, instance: SWEBenchInstance, config: EvalConfig):
        self.instance = instance
        self.config = config
        self.workspace: Optional[Path] = None
        self.container_name: str = f"autopatch_{instance.instance_id}"
        self.test_patch_files: Set[str] = set()
        self._container_running: bool = False
        self._container_path: str = "/testbed"

    @property
    def image_name(self) -> str:
        return f"{self.config.docker_image_prefix}.{self.instance.instance_id}:latest"

    def setup(self) -> Path:
        """Pull image, start container, copy repo locally, apply test_patch."""
        base = Path(self.config.workdir_base) / "workspaces"
        workspace = base / self.instance.instance_id
        self.workspace = workspace

        self._pull_image()
        self._start_container()
        self._copy_repo_to_local(workspace)

        if self.instance.test_patch:
            self._apply_patch(workspace, self.instance.test_patch)
            self.test_patch_files = self._get_changed_files(workspace)

        return workspace

    def cleanup(self) -> None:
        """Stop and remove container; optionally remove image; delete local workspace."""
        if self._container_running:
            _run(["docker", "stop", self.container_name],
                 label="docker stop", check=False)
            _run(["docker", "rm", self.container_name],
                 label="docker rm", check=False)
            self._container_running = False

        if not self.config.keep_image:
            _run(["docker", "rmi", self.image_name],
                 label="docker rmi", check=False)

        if self.workspace and self.workspace.exists():
            shutil.rmtree(self.workspace, ignore_errors=True)

    # ── Private helpers ──────────────────────────────────────────

    def _pull_image(self) -> None:
        logger.info("  [DockerEnv] Pulling %s ...", self.image_name)
        result = _run(
            ["docker", "pull", self.image_name],
            label=f"docker pull {self.image_name}",
            timeout=600,
            check=False,
        )
        if result.returncode != 0:
            raise DockerSetupError(
                f"docker pull failed for {self.image_name}:\n{result.stderr[:500]}"
            )
        logger.info("  [DockerEnv] Pull complete: %s", self.image_name)

    def _start_container(self) -> None:
        # Remove any stale container with the same name
        _run(["docker", "rm", "-f", self.container_name],
             label="docker rm stale", check=False)

        result = _run(
            ["docker", "run", "-d", "--name", self.container_name,
             self.image_name, "sleep", "infinity"],
            label="docker run",
            check=False,
        )
        if result.returncode != 0:
            raise DockerSetupError(
                f"docker run failed:\n{result.stderr[:500]}"
            )
        self._container_running = True
        logger.info("  [DockerEnv] Container %s started", self.container_name)

    def _copy_repo_to_local(self, workspace: Path) -> None:
        workspace.parent.mkdir(parents=True, exist_ok=True)
        if workspace.exists():
            shutil.rmtree(workspace)

        for container_path in _CONTAINER_REPO_PATHS:
            result = _run(
                ["docker", "cp",
                 f"{self.container_name}:{container_path}",
                 str(workspace)],
                label=f"docker cp {container_path}",
                timeout=120,
                check=False,
            )
            if result.returncode == 0:
                self._container_path = container_path
                logger.info(
                    "  [DockerEnv] Copied %s → %s", container_path, workspace
                )
                return

        raise DockerSetupError(
            f"Cannot find repo in container {self.container_name}. "
            f"Tried paths: {_CONTAINER_REPO_PATHS}"
        )

    def _apply_patch(self, workspace: Path, patch_content: str) -> None:
        patch_file = workspace / ".tmp_test_patch.diff"
        patch_file.write_text(patch_content, encoding="utf-8")
        try:
            _run(
                ["git", "apply", "--allow-empty", str(patch_file)],
                cwd=str(workspace),
                label="git apply test_patch",
            )
        finally:
            patch_file.unlink(missing_ok=True)

    def _get_changed_files(self, workspace: Path) -> Set[str]:
        result = subprocess.run(
            ["git", "diff", "HEAD", "--name-only"],
            cwd=str(workspace),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            logger.warning(
                "  [DockerEnv] git diff --name-only failed (exit %d): %s",
                result.returncode,
                result.stderr[:200],
            )
            return set()
        return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def _run(
    cmd: list,
    cwd: Optional[str] = None,
    label: str = "",
    timeout: int = 120,
    check: bool = True,
) -> subprocess.CompletedProcess:
    display = label or " ".join(str(c) for c in cmd[:4])
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if check and result.returncode != 0:
            raise DockerSetupError(
                f"[{display}] exit {result.returncode}\n{result.stderr[:500]}"
            )
        return result
    except subprocess.TimeoutExpired as e:
        raise DockerSetupError(f"[{display}] timed out ({timeout}s)") from e
```

- [ ] **Step 4：运行测试，确认 4 个测试全部通过**

```bash
pytest tests/test_docker_env.py -v
```

期望：4 个测试全部 PASSED

- [ ] **Step 5：运行全量测试确认无回归**

```bash
pytest tests/ -q
```

期望：全部 PASSED

- [ ] **Step 6：提交**

```bash
git add eval/docker_env.py tests/test_docker_env.py
git commit -m "feat: add DockerEnvironment for Docker-based eval setup"
```

---

## Task 3：run_tests_docker 函数

**Files:**
- Modify: `eval/verify.py`
- Create: `tests/test_docker_verify.py`

- [ ] **Step 1：写失败测试**

新建 `tests/test_docker_verify.py`：

```python
"""
tests/test_docker_verify.py
---------------------------
Unit tests for eval/verify.run_tests_docker (subprocess mocked).
"""
from unittest.mock import patch, MagicMock
from eval.verify import run_tests_docker


class TestRunTestsDocker:

    def test_empty_test_ids_returns_empty_dict(self):
        result = run_tests_docker([], "my_container", "/workspace")
        assert result == {}

    def test_docker_cp_is_called_before_exec(self):
        calls = []

        def fake_run(cmd, **kwargs):
            calls.append(cmd)
            m = MagicMock()
            m.returncode = 0
            m.stdout = "1 passed"
            m.stderr = ""
            return m

        with patch("eval.verify.subprocess.run", side_effect=fake_run):
            run_tests_docker(
                ["tests/test_foo.py::test_bar"],
                "autopatch_flask",
                "/tmp/workspace",
                timeout=10,
            )

        # First call must be docker cp (sync workspace to container)
        assert calls[0][0] == "docker"
        assert calls[0][1] == "cp"
        assert "autopatch_flask:/testbed/" in calls[0][2]

        # Second call must be docker exec
        assert calls[1][0] == "docker"
        assert calls[1][1] == "exec"
        assert "autopatch_flask" in calls[1]

    def test_docker_cp_failure_returns_all_false(self):
        def fake_run(cmd, **kwargs):
            m = MagicMock()
            m.returncode = 1  # cp fails
            m.stdout = ""
            m.stderr = "no such container"
            return m

        with patch("eval.verify.subprocess.run", side_effect=fake_run):
            result = run_tests_docker(
                ["tests/test_foo.py::test_bar"],
                "autopatch_flask",
                "/tmp/workspace",
            )

        assert result == {"tests/test_foo.py::test_bar": False}

    def test_pytest_output_parsed_correctly(self):
        pytest_output = (
            "tests/test_foo.py::test_bar PASSED\n"
            "tests/test_foo.py::test_baz FAILED\n"
        )

        def fake_run(cmd, **kwargs):
            m = MagicMock()
            m.returncode = 1
            if "cp" in cmd:
                m.returncode = 0
                m.stdout = ""
                m.stderr = ""
            else:
                m.stdout = pytest_output
                m.stderr = ""
            return m

        with patch("eval.verify.subprocess.run", side_effect=fake_run):
            result = run_tests_docker(
                ["tests/test_foo.py::test_bar", "tests/test_foo.py::test_baz"],
                "autopatch_flask",
                "/tmp/workspace",
            )

        assert result["tests/test_foo.py::test_bar"] is True
        assert result["tests/test_foo.py::test_baz"] is False
```

- [ ] **Step 2：运行测试，确认失败**

```bash
pytest tests/test_docker_verify.py -v
```

期望：`ImportError: cannot import name 'run_tests_docker' from 'eval.verify'`

- [ ] **Step 3：在 `eval/verify.py` 末尾添加 `run_tests_docker`**

在文件最后追加（注意：`subprocess` 已在文件顶部导入，直接使用）：

```python
def run_tests_docker(
    test_ids: List[str],
    container_name: str,
    workspace: str,
    repo: str = "",
    timeout: int = 300,
) -> Dict[str, bool]:
    """
    在 Docker 容器中运行测试。

    流程：
      1. docker cp <workspace>/. <container>:/testbed/  — 同步本地改动到容器
      2. docker exec <container> bash -c "cd /testbed && pytest ..."  — 在容器内跑测试
      3. 复用现有 _parse_pytest_output / _parse_django_output 解析结果

    Args:
        test_ids:       测试标识列表
        container_name: Docker 容器名（如 "autopatch_pallets__flask-4045"）
        workspace:      本地工作目录路径（改动已在此处）
        repo:           仓库名（用于选择 test runner，默认 pytest）
        timeout:        超时秒数

    Returns:
        {test_id: True/False} 字典
    """
    if not test_ids:
        return {}

    # 1. 将本地改动同步回容器
    sync_result = subprocess.run(
        ["docker", "cp", f"{workspace}/.", f"{container_name}:/testbed/"],
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
    inner_cmd = "cd /testbed && " + " ".join(test_cmd_parts)

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
```

同时在 `eval/verify.py` 顶部确认 `import subprocess` 和 `import logging` 已存在（它们已存在，无需新增）。

- [ ] **Step 4：运行测试，确认全部通过**

```bash
pytest tests/test_docker_verify.py -v
```

期望：4 个测试全部 PASSED

- [ ] **Step 5：运行全量测试确认无回归**

```bash
pytest tests/ -q
```

期望：全部 PASSED

- [ ] **Step 6：提交**

```bash
git add eval/verify.py tests/test_docker_verify.py
git commit -m "feat: add run_tests_docker for Docker-based test execution"
```

---

## Task 4：Evaluator 接线 + CLI 更新

**Files:**
- Modify: `eval/evaluator.py`
- Modify: `run_eval.py`

- [ ] **Step 1：修改 `eval/evaluator.py` 的 `evaluate()` 方法**

将 `evaluate()` 方法中的环境创建和测试执行部分替换如下。

找到现有代码：
```python
        env = InstanceEnvironment(self.instance, self.config)
        t0 = time.time()

        try:
            # 1. 搭建环境
            workspace = env.setup()
            workspace_str = str(workspace)

            # 2. 基线验证：FAIL_TO_PASS 应该失败
            if self.instance.fail_to_pass:
                baseline = run_tests(
                    self.instance.fail_to_pass,
                    workspace_str,
                    repo=self.instance.repo,
                    timeout=self.config.timeout_per_instance // 3,
                )
```

替换为：
```python
        # 根据配置选择环境和测试执行器
        if self.config.use_docker:
            from eval.docker_env import DockerEnvironment
            from eval.verify import run_tests_docker
            env = DockerEnvironment(self.instance, self.config)
            def _run_tests(test_ids, ws, **kw):
                return run_tests_docker(
                    test_ids, env.container_name, ws, **kw
                )
        else:
            env = InstanceEnvironment(self.instance, self.config)
            _run_tests = run_tests

        t0 = time.time()

        try:
            # 1. 搭建环境
            workspace = env.setup()
            workspace_str = str(workspace)

            # 2. 基线验证：FAIL_TO_PASS 应该失败
            if self.instance.fail_to_pass:
                baseline = _run_tests(
                    self.instance.fail_to_pass,
                    workspace_str,
                    repo=self.instance.repo,
                    timeout=self.config.timeout_per_instance // 3,
                )
```

然后找到步骤 5 和 6 中的所有 `run_tests(` 调用，改为 `_run_tests(`：

找到：
```python
            # 5. 验证 FAIL_TO_PASS
            if self.instance.fail_to_pass:
                result.fail_to_pass_results = run_tests(
                    self.instance.fail_to_pass,
                    workspace_str,
                    repo=self.instance.repo,
                    timeout=self.config.timeout_per_instance // 2,
                )

            # 6. 验证 PASS_TO_PASS
            if self.instance.pass_to_pass:
                result.pass_to_pass_results = run_tests(
                    self.instance.pass_to_pass,
                    workspace_str,
                    repo=self.instance.repo,
                    timeout=self.config.timeout_per_instance // 2,
                )
```

替换为：
```python
            # 5. 验证 FAIL_TO_PASS
            if self.instance.fail_to_pass:
                result.fail_to_pass_results = _run_tests(
                    self.instance.fail_to_pass,
                    workspace_str,
                    repo=self.instance.repo,
                    timeout=self.config.timeout_per_instance // 2,
                )

            # 6. 验证 PASS_TO_PASS
            if self.instance.pass_to_pass:
                result.pass_to_pass_results = _run_tests(
                    self.instance.pass_to_pass,
                    workspace_str,
                    repo=self.instance.repo,
                    timeout=self.config.timeout_per_instance // 2,
                )
```

- [ ] **Step 2：更新 `run_eval.py` 的 `_check_env` 函数，在 Docker 模式下验证 Docker 可用**

在 `run_eval.py` 的 `_check_env()` 函数末尾追加：

```python
    # Docker 模式下检查 Docker 是否可用
    if config.use_docker:
        import subprocess as _sp
        r = _sp.run(["docker", "info"], capture_output=True)
        if r.returncode != 0:
            logger.error("[Error] Docker 未启动或未安装，--docker 模式需要 Docker Desktop 运行")
            sys.exit(1)
        logger.info("[OK] Docker 可用")
```

但 `_check_env` 目前没有接收 `config` 参数，需要先修改签名。找到：

```python
def _check_env() -> None:
    """检查必要的环境变量和依赖。"""
    import os
    from dotenv import load_dotenv
```

替换为：

```python
def _check_env(config=None) -> None:
    """检查必要的环境变量和依赖。"""
    import os
    from dotenv import load_dotenv
```

然后找到 `_check_env()` 的调用处（`main()` 函数内），改为 `_check_env(config)`：

找到：
```python
    # 环境检查
    _check_env()
```

替换为：
```python
    # 环境检查
    _check_env(config)
```

在函数末尾追加 Docker 检查块：

```python
    # Docker 模式下检查 Docker 是否可用
    if config is not None and config.use_docker:
        import subprocess as _sp
        r = _sp.run(["docker", "info"], capture_output=True)
        if r.returncode != 0:
            logger.error(
                "[Error] Docker 未启动或未安装，--docker 模式需要 Docker Desktop 运行"
            )
            sys.exit(1)
        logger.info("[OK] Docker 可用")
```

- [ ] **Step 3：运行全量测试确认无回归**

```bash
pytest tests/ -q
```

期望：全部 PASSED（Docker 模式未激活，现有测试不受影响）

- [ ] **Step 4：提交**

```bash
git add eval/evaluator.py run_eval.py
git commit -m "feat: wire Docker env and test runner into evaluator"
```

---

## 验收

安装 Docker Desktop 后，运行：

```bash
# 验证 Docker 模式启动正常（会拉取约 2-5GB 镜像）
python run_eval.py --instance-ids pallets__flask-4045 --docker

# 跑完后查看结果
cat eval/results/*/report.json
```

期望：`status` 不再是因依赖冲突导致的 `failed`，Agent 能正常运行且测试在正确环境中执行。
