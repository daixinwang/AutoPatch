from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple

from eval.config import EvalConfig
from eval.dataset import SWEBenchInstance
from eval.instance_env import InstanceEnvironment
from eval.unified_models import PreparedWorkspace, UnifiedCase


class LocalFixturePreparer:
    def __init__(self, run_dir: Path, project_root: Optional[Path] = None):
        self.run_dir = run_dir
        self.project_root = project_root or Path(__file__).resolve().parents[1]

    def prepare(self, case: UnifiedCase) -> PreparedWorkspace:
        if case.fixture_path is None:
            raise ValueError(f"{case.case_id} has no fixture_path")

        workspace = self.run_dir / "workspaces" / case.case_id
        if workspace.exists():
            shutil.rmtree(workspace, ignore_errors=True)

        fixture_path = case.fixture_path
        if not fixture_path.is_absolute():
            fixture_path = self.project_root / fixture_path

        shutil.copytree(fixture_path, workspace)
        base_commit = _init_git_baseline(workspace)

        return PreparedWorkspace(
            workspace=workspace,
            base_commit=base_commit,
            cleanup=lambda: shutil.rmtree(workspace, ignore_errors=True),
        )


class SWEBenchPreparer:
    def __init__(self, config: EvalConfig):
        self.config = config

    def prepare(self, case: UnifiedCase) -> PreparedWorkspace:
        instance = SWEBenchInstance(
            instance_id=case.swebench_instance_id or case.case_id,
            repo=case.repo,
            base_commit=case.base_commit or "",
            problem_statement=case.issue_body,
            test_patch=case.swebench_test_patch,
            patch=case.swebench_gold_patch,
            fail_to_pass=case.fail_to_pass,
            pass_to_pass=case.pass_to_pass,
            version=case.version,
            environment_setup_commit=case.environment_setup_commit,
        )

        if self.config.use_docker:
            from eval.docker_env import DockerEnvironment

            env = DockerEnvironment(instance, self.config)
        else:
            env = InstanceEnvironment(instance, self.config)

        workspace = env.setup()

        base_commit, error = _git_output(workspace, ["git", "rev-parse", "HEAD"])
        if not base_commit:
            if case.base_commit:
                base_commit = case.base_commit
            else:
                raise RuntimeError(
                    "Unable to determine base commit from workspace and no case.base_commit was provided: "
                    f"git rev-parse failed: {error or 'unknown error'}"
                )

        return PreparedWorkspace(
            workspace=workspace,
            base_commit=base_commit,
            test_patch_files=set(env.test_patch_files),
            cleanup=env.cleanup,
            docker_container=getattr(env, "container_name", None),
            docker_container_path=getattr(env, "_container_path", None),
        )


def _init_git_baseline(workspace: Path) -> str:
    git_env = {
        **os.environ,
        "GIT_AUTHOR_NAME": "AutoPatch Eval",
        "GIT_AUTHOR_EMAIL": "autopatch-eval@example.local",
        "GIT_COMMITTER_NAME": "AutoPatch Eval",
        "GIT_COMMITTER_EMAIL": "autopatch-eval@example.local",
    }

    subprocess.run(["git", "init"], cwd=workspace, check=True, env=git_env, capture_output=True, text=True)
    subprocess.run(["git", "add", "."], cwd=workspace, check=True, env=git_env, capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "--allow-empty", "-m", "baseline"],
        cwd=workspace,
        check=True,
        env=git_env,
        capture_output=True,
        text=True,
    )

    base_commit, error = _git_output(workspace, ["git", "rev-parse", "HEAD"])
    if not base_commit:
        raise RuntimeError(
            "Failed to initialize local fixture baseline commit: "
            f"git rev-parse failed: {error or 'unknown error'}"
        )
    return base_commit


def _git_output(cwd: Path, cmd: List[str]) -> Tuple[str, str]:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if result.returncode != 0:
        return "", result.stderr.strip()
    return result.stdout.strip(), ""
