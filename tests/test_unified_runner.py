from pathlib import Path
import shutil
import subprocess

import pytest

from eval.unified_models import UnifiedCase
from eval.config import EvalConfig
from eval.unified_preparers import LocalFixturePreparer, SWEBenchPreparer


def _git_baseline(workspace: Path) -> str:
    result = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=workspace,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def test_local_fixture_preparer_creates_git_baseline(tmp_path):
    case = UnifiedCase(
        case_id="py-single-file",
        dataset_name="sanity-v1",
        source="local_sanity",
        repo="local/sanity-py-single-file",
        base_commit=None,
        issue_title="Percentage discounts are 100x too large",
        issue_body="Fix the discount calculation.",
        language="Python",
        fail_to_pass=["tests/test_calculator.py::test_percentage_discount_uses_percent_units"],
        pass_to_pass=["tests/test_calculator.py::test_zero_discount_keeps_subtotal"],
        fixture_path=Path("eval/fixtures/sanity-v1/py-single-file"),
    )

    prepared = LocalFixturePreparer(tmp_path).prepare(case)

    assert prepared.workspace == tmp_path / "workspaces" / "py-single-file"
    assert len(prepared.base_commit) == 40
    assert (prepared.workspace / ".git").exists()
    assert (prepared.workspace / "autopatch_demo" / "calculator.py").exists()
    assert prepared.cleanup is not None

    prepared.cleanup()
    assert not prepared.workspace.exists()


def test_local_fixture_preparer_resolves_fixture_from_repo_root_when_cwd_changes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    case = UnifiedCase(
        case_id="py-single-file",
        dataset_name="sanity-v1",
        source="local_sanity",
        repo="local/sanity-py-single-file",
        base_commit=None,
        issue_title="Percentage discounts are 100x too large",
        issue_body="Fix the discount calculation.",
        language="Python",
        fail_to_pass=["tests/test_calculator.py::test_percentage_discount_uses_percent_units"],
        pass_to_pass=["tests/test_calculator.py::test_zero_discount_keeps_subtotal"],
        fixture_path=Path("eval/fixtures/sanity-v1/py-single-file"),
    )

    prepared = LocalFixturePreparer(tmp_path).prepare(case)

    assert prepared.workspace == tmp_path / "workspaces" / "py-single-file"
    assert (prepared.workspace / "autopatch_demo" / "calculator.py").exists()


def test_local_fixture_preparer_allows_empty_fixture(tmp_path):
    empty_fixture = tmp_path / "empty_fixture"
    empty_fixture.mkdir()
    case = UnifiedCase(
        case_id="empty-fixture",
        dataset_name="sanity-v1",
        source="local_sanity",
        repo="local/empty",
        base_commit=None,
        issue_title="Empty fixture",
        issue_body="Can build an empty baseline",
        language="Python",
        fail_to_pass=[],
        pass_to_pass=[],
        fixture_path=empty_fixture,
    )

    prepared = LocalFixturePreparer(tmp_path).prepare(case)

    assert len(prepared.base_commit) == 40
    assert _git_baseline(prepared.workspace) == prepared.base_commit
    prepared.cleanup()


def test_local_fixture_preparer_requires_fixture_path(tmp_path):
    case = UnifiedCase(
        case_id="missing-fixture",
        dataset_name="sanity-v1",
        source="local_sanity",
        repo="local/missing",
        base_commit=None,
        issue_title="Missing fixture",
        issue_body="No fixture path.",
        language="Python",
        fail_to_pass=[],
        pass_to_pass=[],
    )

    with pytest.raises(ValueError, match="missing-fixture has no fixture_path"):
        LocalFixturePreparer(tmp_path).prepare(case)


def test_swebench_preparer_uses_instance_environment(monkeypatch, tmp_path):
    captured = {}

    class FakeInstanceEnvironment:
        def __init__(self, instance, config):
            self.instance = instance
            self.config = config
            self.workspace = tmp_path / "workspaces" / instance.instance_id
            self.test_patch_files = {"tests/test_fake.py"}
            self.cleaned = False
            self.base_commit = None
            captured["env"] = self

        def setup(self):
            if self.workspace.exists():
                shutil.rmtree(self.workspace, ignore_errors=True)
            self.workspace.mkdir(parents=True)
            subprocess.run(["git", "init"], cwd=self.workspace, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=self.workspace, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "commit", "--allow-empty", "-m", "baseline"],
                cwd=self.workspace,
                check=True,
                capture_output=True,
                text=True,
            )
            rev = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                check=True,
            )
            self.base_commit = rev.stdout.strip()
            return self.workspace

        def cleanup(self):
            self.cleaned = True
            if self.workspace.exists():
                shutil.rmtree(self.workspace, ignore_errors=True)

    monkeypatch.setattr("eval.unified_preparers.InstanceEnvironment", FakeInstanceEnvironment)

    case = UnifiedCase(
        case_id="sympy__sympy-1337",
        dataset_name="swebench",
        source="swe_bench",
        repo="sympy/sympy",
        base_commit=None,
        issue_title="SWE-bench issue sympy__sympy-1337",
        issue_body="Fix simplify behavior.",
        language="Python",
        fail_to_pass=["tests.test_sympy.py::test_bug"],
        pass_to_pass=[],
        swebench_instance_id="sympy__sympy-1337",
        swebench_test_patch="diff --git a/tests/test.py b/tests/test.py\n",
        swebench_gold_patch="gold patch",
    )

    prepared = SWEBenchPreparer(EvalConfig(use_docker=False)).prepare(case)
    env = captured["env"]

    assert prepared.workspace == tmp_path / "workspaces" / "sympy__sympy-1337"
    assert prepared.base_commit == env.base_commit
    assert prepared.test_patch_files == {"tests/test_fake.py"}
    assert prepared.cleanup.__self__ is env
    assert prepared.docker_container is None
    assert prepared.docker_container_path is None

    prepared.cleanup()
    assert env.cleaned is True
    assert not prepared.workspace.exists()


def test_swebench_preparer_propagates_docker_container_info(monkeypatch, tmp_path):
    captured = {}

    class FakeDockerEnvironment:
        def __init__(self, instance, config):
            self.instance = instance
            self.config = config
            self.workspace = tmp_path / "workspaces" / instance.instance_id
            self.test_patch_files = {"tests/docker_test.py"}
            self.cleaned = False
            self.base_commit = None
            self.container_name = "fake-container"
            self._container_path = "/repo"
            captured["env"] = self

        def setup(self):
            if self.workspace.exists():
                shutil.rmtree(self.workspace, ignore_errors=True)
            self.workspace.mkdir(parents=True)
            subprocess.run(["git", "init"], cwd=self.workspace, check=True, capture_output=True, text=True)
            subprocess.run(["git", "add", "."], cwd=self.workspace, check=True, capture_output=True, text=True)
            subprocess.run(
                ["git", "commit", "--allow-empty", "-m", "baseline"],
                cwd=self.workspace,
                check=True,
                capture_output=True,
                text=True,
            )
            rev = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                check=True,
            )
            self.base_commit = rev.stdout.strip()
            return self.workspace

        def cleanup(self):
            self.cleaned = True
            if self.workspace.exists():
                shutil.rmtree(self.workspace, ignore_errors=True)

    monkeypatch.setattr("eval.docker_env.DockerEnvironment", FakeDockerEnvironment)

    case = UnifiedCase(
        case_id="pallets__flask-4045",
        dataset_name="swebench",
        source="swe_bench",
        repo="pallets/flask",
        base_commit=None,
        issue_title="SWE-bench issue pallets__flask-4045",
        issue_body="Fix a flask bug.",
        language="Python",
        fail_to_pass=["tests/test_flask.py::test_bug"],
        pass_to_pass=[],
        swebench_instance_id="pallets__flask-4045",
    )

    prepared = SWEBenchPreparer(EvalConfig(use_docker=True)).prepare(case)
    env = captured["env"]

    assert prepared.workspace == tmp_path / "workspaces" / "pallets__flask-4045"
    assert prepared.base_commit == env.base_commit
    assert prepared.test_patch_files == {"tests/docker_test.py"}
    assert prepared.docker_container == "fake-container"
    assert prepared.docker_container_path == "/repo"
    assert prepared.cleanup.__self__ is env
