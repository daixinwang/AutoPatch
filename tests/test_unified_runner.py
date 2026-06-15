import json
from pathlib import Path
import shutil
import subprocess

import pytest

from eval.config import EvalConfig
from eval.unified_providers import LocalSanityProvider
from eval.unified_runner import UnifiedEvalRunner
from eval.unified_models import PreparedWorkspace, UnifiedCase
from eval.unified_preparers import LocalFixturePreparer, SWEBenchPreparer


def test_unified_runner_baseline_only_writes_protocol_artifacts(tmp_path):
    cases = LocalSanityProvider(
        dataset_name="sanity-v1",
        cases_dir=Path("eval/cases/sanity-v1"),
    ).load()
    selected = [case for case in cases if case.case_id == "py-single-file"]

    runner = UnifiedEvalRunner(
        cases=selected,
        run_id="baseline-run",
        results_dir=tmp_path,
        mode="baseline-only",
    )
    report = runner.run()

    case_dir = tmp_path / "baseline-run" / "cases" / "py-single-file"
    verdict = json.loads((case_dir / "verdict.json").read_text(encoding="utf-8"))
    report_json = json.loads((tmp_path / "baseline-run" / "report.json").read_text(encoding="utf-8"))
    config = json.loads((tmp_path / "baseline-run" / "config.json").read_text(encoding="utf-8"))

    assert report["baseline_ready"] == 1
    assert report_json["resolved_rate_all"] == 0.0
    assert report_json["resolved_rate_valid"] == 0.0
    assert verdict["verdict"] == "baseline_ready"
    assert config["protocol_version"] == "2026-06-14"
    assert config["run_id"] == "baseline-run"
    assert "autopatch_commit" in config
    assert "autopatch_dirty" in config
    assert config["dataset_name"] == "sanity-v1"
    assert config["dataset_version"] == "2026-06-14"
    assert config["case_ids"] == ["py-single-file"]
    assert config["agent_config"]["mode"] == "baseline-only"
    assert config["agent_config"]["planner_model"]
    assert config["agent_config"]["coder_model"]
    assert config["agent_config"]["test_runner_model"]
    assert config["agent_config"]["reviewer_model"]
    assert config["agent_config"]["temperature"] == 0
    assert config["agent_config"]["max_review_retries"] == 3
    assert config["agent_config"]["max_coder_steps"] == 40
    assert "rag_enabled" in config["agent_config"]
    assert "reviewer_enabled" in config["agent_config"]
    assert config["environment"]["os"] in {"macOS", "Darwin", "Linux", "Windows"}
    assert "architecture" in config["environment"]
    assert "python_version" in config["environment"]
    assert config["environment"]["docker_enabled"] is False
    assert "docker_platform" in config["environment"]
    assert config["timeouts"]["agent_seconds"] is None
    assert config["timeouts"]["test_seconds"] == 15
    assert config["timeouts"]["case_seconds"] == 30
    assert (case_dir / "case.json").exists()
    assert (case_dir / "issue.md").exists()
    assert (case_dir / "test-before.log").exists()
    assert (tmp_path / "baseline-run" / "report.json").exists()
    assert (tmp_path / "baseline-run" / "report.md").exists()


def test_unified_runner_baseline_failure_category_is_preserved_in_report(tmp_path):
    cases = LocalSanityProvider(
        dataset_name="sanity-v1",
        cases_dir=Path("eval/cases/sanity-v1"),
    ).load()
    selected = [case for case in cases if case.case_id == "invalid-baseline"]

    runner = UnifiedEvalRunner(
        cases=selected,
        run_id="invalid-baseline-run",
        results_dir=tmp_path,
        mode="baseline-only",
    )
    report = runner.run()

    case_dir = tmp_path / "invalid-baseline-run" / "cases" / "invalid-baseline"
    verdict = json.loads((case_dir / "verdict.json").read_text(encoding="utf-8"))

    assert report["cases"][0]["failure_category"] == verdict["failure_category"]
    assert report["cases"][0]["failure_category"] == "invalid_case"


def test_unified_runner_mock_patch_resolves_case(tmp_path):
    cases = LocalSanityProvider(
        dataset_name="sanity-v1",
        cases_dir=Path("eval/cases/sanity-v1"),
    ).load()
    selected = [case for case in cases if case.case_id == "py-single-file"]

    runner = UnifiedEvalRunner(
        cases=selected,
        run_id="mock-run",
        results_dir=tmp_path,
        mode="mock-patch",
        mock_patch_dir=Path("eval/mock_patches/sanity-v1/resolved"),
    )
    report = runner.run()

    case_dir = tmp_path / "mock-run" / "cases" / "py-single-file"
    verdict = json.loads((case_dir / "verdict.json").read_text(encoding="utf-8"))
    changed = json.loads((case_dir / "changed-files.json").read_text(encoding="utf-8"))

    assert report["resolved"] == 1
    assert verdict["verdict"] == "resolved"
    assert changed == [
        {
            "path": "autopatch_demo/calculator.py",
            "is_test": False,
            "change_type": "modified",
        }
    ]
    assert (case_dir / "patch.diff").read_text(encoding="utf-8").strip()
    assert (case_dir / "test-after.log").exists()


def test_unified_runner_agent_failure_is_failed(tmp_path, monkeypatch):
    cases = LocalSanityProvider(
        dataset_name="sanity-v1",
        cases_dir=Path("eval/cases/sanity-v1"),
    ).load()
    selected = [case for case in cases if case.case_id == "py-single-file"]

    import autopatch

    def boom(*args, **kwargs):
        raise RuntimeError("agent exploded")

    monkeypatch.setattr(autopatch, "run_agent_on_issue", boom)

    runner = UnifiedEvalRunner(
        cases=selected,
        run_id="agent-failure",
        results_dir=tmp_path,
        mode="agent",
    )
    report = runner.run()

    case_dir = tmp_path / "agent-failure" / "cases" / "py-single-file"
    verdict = json.loads((case_dir / "verdict.json").read_text(encoding="utf-8"))

    assert report["failed"] == 1
    assert report["infra_error"] == 0
    assert verdict["verdict"] == "failed"
    assert verdict["failure_category"] == "tool_failure"
    assert verdict["patch_applies"] is False
    assert verdict["modified_test_files"] is False
    assert report["cases"][0]["verdict"] == "failed"


def test_unified_runner_case_timeout_reports_agent_timeout(tmp_path, monkeypatch):
    cases = LocalSanityProvider(
        dataset_name="sanity-v1",
        cases_dir=Path("eval/cases/sanity-v1"),
    ).load()
    selected = [case for case in cases if case.case_id == "py-single-file"]

    runner = UnifiedEvalRunner(
        cases=selected,
        run_id="case-timeout",
        results_dir=tmp_path,
        mode="baseline-only",
        eval_config=EvalConfig(timeout_per_instance=1),
    )
    runner.case_timeout_seconds = 0.05

    import time

    def slow_baseline(case, prepared, case_dir):
        time.sleep(0.2)
        return {
            "verdict": "baseline_ready",
            "reason": "Baseline is valid: FAIL_TO_PASS failed and PASS_TO_PASS passed before patch.",
        }

    monkeypatch.setattr(runner, "_run_baseline", slow_baseline)

    report = runner.run()
    case_dir = tmp_path / "case-timeout" / "cases" / "py-single-file"
    verdict = json.loads((case_dir / "verdict.json").read_text(encoding="utf-8"))
    report_json = json.loads((tmp_path / "case-timeout" / "report.json").read_text(encoding="utf-8"))

    assert report["agent_timeout"] == 1
    assert report_json["agent_timeout"] == 1
    assert verdict["verdict"] == "agent_timeout"
    assert verdict["failure_category"] == "timeout"
    assert verdict["patch_applies"] is False
    assert verdict["modified_test_files"] is False
    assert "Case execution timed out" in verdict["reason"]
    assert "tool_timeout" not in (case_dir / "verdict.json").read_text(encoding="utf-8")
    assert "| Agent timeout | 1 |" in (tmp_path / "case-timeout" / "report.md").read_text(encoding="utf-8")


def test_unified_runner_timeout_failure_category_uses_protocol_value(tmp_path, monkeypatch):
    cases = LocalSanityProvider(
        dataset_name="sanity-v1",
        cases_dir=Path("eval/cases/sanity-v1"),
    ).load()
    selected = [case for case in cases if case.case_id == "py-single-file"]

    runner = UnifiedEvalRunner(
        cases=selected,
        run_id="timeout-run",
        results_dir=tmp_path,
        mode="agent",
        eval_config=EvalConfig(timeout_per_instance=2),
    )

    import autopatch

    def fake_agent(*args, **kwargs):
        workspace = tmp_path / "timeout-run" / "workspaces" / "py-single-file"
        file_path = workspace / "autopatch_demo" / "calculator.py"
        original = file_path.read_text(encoding="utf-8")
        file_path.write_text(original.replace("discount_percent", "discount_percent / 100"), encoding="utf-8")
        return {"review_result": "", "step_count": 0}

    monkeypatch.setattr(autopatch, "run_agent_on_issue", fake_agent)

    calls = {"count": 0}

    def fake_run_selectors(workspace, selectors):
        calls["count"] += 1
        if calls["count"] <= 2:
            return {
                selector: {
                    "passed": selector.endswith("zero_discount_keeps_subtotal"),
                    "returncode": 0 if selector.endswith("zero_discount_keeps_subtotal") else 1,
                    "stdout": "",
                    "stderr": "",
                    "timed_out": False,
                }
                for selector in selectors
            }
        return {
            selector: {
                "passed": False,
                "returncode": -1,
                "stdout": "",
                "stderr": "",
                "timed_out": True,
            }
            for selector in selectors
        }

    monkeypatch.setattr(runner, "_run_selectors", fake_run_selectors)

    report = runner.run()
    case_dir = tmp_path / "timeout-run" / "cases" / "py-single-file"
    verdict = json.loads((case_dir / "verdict.json").read_text(encoding="utf-8"))

    assert report["failed"] == 1
    assert report["infra_error"] == 0
    assert verdict["failure_category"] == "timeout"
    assert "tool_timeout" not in (case_dir / "verdict.json").read_text(encoding="utf-8")


def test_unified_runner_uses_docker_for_selectors_when_container_is_available(tmp_path, monkeypatch):
    calls = []

    def fail_local_pytest(*args, **kwargs):
        raise AssertionError("local pytest should not run for docker workspaces")

    def fake_run_tests_docker(test_ids, container_name, workspace, repo="", timeout=300, container_path="/testbed"):
        calls.append(
            {
                "test_ids": test_ids,
                "container_name": container_name,
                "workspace": workspace,
                "repo": repo,
                "timeout": timeout,
                "container_path": container_path,
            }
        )
        return {test_id: True for test_id in test_ids}

    monkeypatch.setattr(subprocess, "run", fail_local_pytest)
    monkeypatch.setattr("eval.verify.run_tests_docker", fake_run_tests_docker)

    runner = UnifiedEvalRunner(
        cases=[],
        run_id="docker-selectors",
        results_dir=tmp_path,
        mode="baseline-only",
        eval_config=EvalConfig(timeout_per_instance=123),
    )
    prepared = PreparedWorkspace(
        workspace=tmp_path / "workspace",
        base_commit="abc123",
        docker_container="fake-container",
        docker_container_path="/repo",
    )

    results = runner._run_selectors(prepared, ["tests/test_fake.py::test_ok"])

    assert calls == [
        {
            "test_ids": ["tests/test_fake.py::test_ok"],
            "container_name": "fake-container",
            "workspace": str(tmp_path / "workspace"),
            "repo": "",
            "timeout": runner.selector_timeout_seconds,
            "container_path": "/repo",
        }
    ]
    assert results["tests/test_fake.py::test_ok"]["passed"] is True
    assert results["tests/test_fake.py::test_ok"]["returncode"] == 0
    assert results["tests/test_fake.py::test_ok"]["stdout"] == ""
    assert results["tests/test_fake.py::test_ok"]["stderr"] == ""
    assert results["tests/test_fake.py::test_ok"]["timed_out"] is False


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
