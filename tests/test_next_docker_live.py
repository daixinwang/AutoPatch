"""Opt-in integration checks: build sandbox.Dockerfile and enable the flag."""

import os
import subprocess

import pytest

pytestmark = pytest.mark.skipif(os.getenv("AUTOPATCH_RUN_DOCKER_TESTS") != "1", reason="Docker integration is opt-in")


def test_live_docker_isolation_and_cleanup(tmp_path):
    from core.execution.docker import DockerSandboxBackend

    (tmp_path / "source.txt").write_text("original")
    backend = DockerSandboxBackend(os.getenv("AUTOPATCH_TEST_IMAGE", "autopatch-sandbox:latest"))
    result = backend.run(
        [
            "/bin/sh",
            "-c",
            (
                'test "$(id -u)" != 0 && test -z "$OPENAI_API_KEY" && test -z "$GITHUB_TOKEN" && '
                'echo "container only" > source.txt && test ! -e /var/run/docker.sock && echo isolated'
            ),
        ],
        tmp_path,
        30,
    )
    assert result.status == "passed", result.model_dump()
    assert "isolated" in result.stdout_summary
    assert (tmp_path / "source.txt").read_text() == "original"


def test_live_docker_timeout_removes_container(tmp_path):
    from core.execution.docker import DockerSandboxBackend

    result = DockerSandboxBackend(os.getenv("AUTOPATCH_TEST_IMAGE", "autopatch-sandbox:latest")).run(
        ["/bin/sh", "-c", "sleep 60"], tmp_path, 2
    )
    assert result.status == "timeout"
    remaining = subprocess.run(
        ["docker", "ps", "-aq", "--filter", "name=autopatch-test-"], capture_output=True, text=True, check=True
    )
    assert not remaining.stdout.strip()


def test_live_pytest_reports_failure_then_success(tmp_path):
    from agent.models import TestPlan
    from core.execution.docker import DockerSandboxBackend
    from core.project_profile import profile_project
    from core.test_pipeline import execute_plan

    (tmp_path / "pyproject.toml").write_text("")
    (tmp_path / "calc.py").write_text("def add(a, b): return a - b\n")
    (tmp_path / "test_calc.py").write_text("from calc import add\ndef test_add(): assert add(2, 3) == 5\n")
    profile = profile_project(tmp_path)
    plan = TestPlan(commands=["python_pytest"], reason="Live regression check")
    backend = DockerSandboxBackend("autopatch-sandbox:latest")
    before = execute_plan(profile, plan, tmp_path, backend)
    assert not before.all_required_passed
    assert before.results[0].exit_code == 1, before.model_dump()
    (tmp_path / "calc.py").write_text("def add(a, b): return a + b\n")
    after = execute_plan(profile, plan, tmp_path, backend)
    assert after.all_required_passed, after.model_dump()
