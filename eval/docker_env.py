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
