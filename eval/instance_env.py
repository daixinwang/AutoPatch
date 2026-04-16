"""
eval/instance_env.py
--------------------
单个 SWE-bench 实例的环境搭建：
  clone → checkout base_commit → apply test_patch → install deps → 基线验证
使用 git worktree 策略复用 clone。
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

import logging

from eval.config import EvalConfig
from eval.dataset import SWEBenchInstance

logger = logging.getLogger(__name__)

# ── Repo 特定安装配置 ──
REPO_INSTALL_MAP: Dict[str, Dict] = {
    "django/django": {
        "pre_install": ["pip install pytz asgiref sqlparse"],
        "install": "pip install -e .",
    },
    "scikit-learn/scikit-learn": {
        "pre_install": ["pip install numpy scipy cython"],
        "install": "pip install --no-build-isolation -e .",
    },
    "sympy/sympy": {
        "install": "pip install -e .",
    },
    "matplotlib/matplotlib": {
        "pre_install": ["pip install numpy"],
        "install": "pip install -e .",
    },
    "requests/requests": {
        "install": "pip install -e .",
    },
    "sphinx-doc/sphinx": {
        "install": "pip install -e .[test]",
    },
    "pallets/flask": {
        "install": "pip install -e .",
    },
    "astropy/astropy": {
        "pre_install": ["pip install numpy cython"],
        "install": "pip install -e .",
    },
    "pylint-dev/pylint": {
        "install": "pip install -e .",
    },
    "pytest-dev/pytest": {
        "install": "pip install -e .",
    },
    "pydata/xarray": {
        "pre_install": ["pip install numpy pandas"],
        "install": "pip install -e .",
    },
    "mwaskom/seaborn": {
        "pre_install": ["pip install numpy pandas matplotlib"],
        "install": "pip install -e .",
    },
}


class InstanceEnvironment:
    """管理单个 SWE-bench 实例的文件系统和运行时环境。"""

    def __init__(self, instance: SWEBenchInstance, config: EvalConfig):
        self.instance = instance
        self.config = config
        self.workspace: Optional[Path] = None
        self._worktree_created = False

    def setup(self) -> Path:
        """
        完整的环境搭建流程，返回 workspace 路径。

        Raises:
            SetupError: 环境搭建失败
        """
        repo_slug = self.instance.repo.replace("/", "__")
        base = Path(self.config.workdir_base)

        # 1. clone / 复用缓存
        repo_cache = base / "repos" / repo_slug
        self._ensure_clone(repo_cache)

        # 2. 创建 worktree
        workspace = base / "workspaces" / self.instance.instance_id
        self._create_worktree(repo_cache, workspace)
        self.workspace = workspace
        self._worktree_created = True

        # 3. apply test_patch
        if self.instance.test_patch:
            self._apply_patch(workspace, self.instance.test_patch, label="test_patch")

        # 4. 安装依赖
        if self.config.install_deps:
            self._install_deps(workspace)

        return workspace

    def cleanup(self) -> None:
        """清理 worktree（保留 repo 缓存 clone）。"""
        if not self._worktree_created or self.workspace is None:
            return
        repo_slug = self.instance.repo.replace("/", "__")
        repo_cache = Path(self.config.workdir_base) / "repos" / repo_slug

        try:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(self.workspace)],
                cwd=str(repo_cache),
                capture_output=True,
                timeout=30,
            )
        except Exception:
            # 回退：直接删除目录
            if self.workspace.exists():
                shutil.rmtree(self.workspace, ignore_errors=True)

        self._worktree_created = False

    # ── 内部方法 ──

    def _ensure_clone(self, repo_cache: Path) -> None:
        """确保 repo_cache 下有完整的 clone，如已存在则 fetch。"""
        repo_cache.parent.mkdir(parents=True, exist_ok=True)

        if (repo_cache / ".git").exists() or (repo_cache / "HEAD").exists():
            # 已有 clone → 尝试 fetch（失败不阻塞，SWE-bench 用历史 commit，本地通常已有）
            _run(
                ["git", "fetch", "--all"],
                cwd=str(repo_cache),
                label=f"git fetch {self.instance.repo}",
                check=False,
            )
        else:
            url = f"https://github.com/{self.instance.repo}.git"
            _run(
                ["git", "clone", "--bare", url, str(repo_cache)],
                label=f"git clone {self.instance.repo}",
                timeout=300,
            )

    def _create_worktree(self, repo_cache: Path, workspace: Path) -> None:
        """从 bare clone 创建 worktree 并 checkout 到 base_commit。"""
        if workspace.exists():
            # 清理残留
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(workspace)],
                cwd=str(repo_cache),
                capture_output=True,
            )
            if workspace.exists():
                shutil.rmtree(workspace, ignore_errors=True)

        workspace.parent.mkdir(parents=True, exist_ok=True)

        branch_name = f"eval-{self.instance.instance_id}"

        # 删除可能残留的同名分支
        subprocess.run(
            ["git", "branch", "-D", branch_name],
            cwd=str(repo_cache),
            capture_output=True,
        )

        _run(
            [
                "git", "worktree", "add",
                "-b", branch_name,
                str(workspace),
                self.instance.base_commit,
            ],
            cwd=str(repo_cache),
            label=f"git worktree add {self.instance.instance_id}",
        )

    def _apply_patch(self, workspace: Path, patch_content: str, label: str = "patch") -> None:
        """Apply a patch via git apply。"""
        patch_file = workspace / f".tmp_{label}.diff"
        patch_file.write_text(patch_content, encoding="utf-8")
        try:
            _run(
                ["git", "apply", "--allow-empty", str(patch_file)],
                cwd=str(workspace),
                label=f"git apply {label}",
            )
        finally:
            patch_file.unlink(missing_ok=True)

    def _install_deps(self, workspace: Path) -> None:
        """安装 repo 特定依赖。"""
        repo = self.instance.repo
        install_cfg = REPO_INSTALL_MAP.get(repo, {"install": "pip install -e ."})

        # 确保 pytest 可用（Agent TestRunner 和 eval verify 都需要）
        _run(
            ["pip", "install", "pytest"],
            cwd=str(workspace),
            label="install pytest",
            timeout=120,
            check=False,
        )

        for cmd_str in install_cfg.get("pre_install", []):
            _run(
                cmd_str.split(),
                cwd=str(workspace),
                label=f"pre_install: {cmd_str}",
                timeout=300,
                check=False,
            )

        install_cmd = install_cfg.get("install", "pip install -e .")
        _run(
            install_cmd.split(),
            cwd=str(workspace),
            label=f"install: {install_cmd}",
            timeout=600,
            check=False,
        )


class SetupError(Exception):
    """环境搭建失败。"""


def _run(
    cmd: List[str],
    cwd: Optional[str] = None,
    label: str = "",
    timeout: int = 120,
    check: bool = True,
) -> subprocess.CompletedProcess:
    """执行子进程，统一错误处理。"""
    display = label or " ".join(cmd[:4])
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if check and result.returncode != 0:
            raise SetupError(
                f"[{display}] 退出码 {result.returncode}\n"
                f"stderr: {result.stderr[:500]}"
            )
        return result
    except subprocess.TimeoutExpired as e:
        raise SetupError(f"[{display}] 超时 ({timeout}s)") from e
