import importlib

import pytest


def next_module(name):
    assert importlib.util.find_spec(name) is not None, f"Missing Next component: {name}"
    return importlib.import_module(name)


@pytest.mark.parametrize(
    "manifest,content,language,command",
    [
        ("pyproject.toml", "", "Python", "python_pytest"),
        ("package.json", '{"scripts":{"test":"vitest"}}', "Node", "node_npm_test"),
        ("go.mod", "module example", "Go", "go_test_all"),
        ("Cargo.toml", "", "Rust", "cargo_test"),
        ("pom.xml", "", "Java", "maven_test"),
        ("build.gradle", "", "Java", "gradle_test"),
        ("Makefile", "test:\n", "Generic", "make_test"),
    ],
)
def test_profile(tmp_path, manifest, content, language, command):
    module = next_module("core.project_profile")
    (tmp_path / manifest).write_text(content)
    profile = module.profile_project(tmp_path)
    assert profile.primary_language == language
    assert command in profile.default_test_commands


def test_reject_foreign_command_and_escape(tmp_path):
    module = next_module("core.test_pipeline")
    models = next_module("agent.models")
    (tmp_path / "pyproject.toml").touch()
    profile = next_module("core.project_profile").profile_project(tmp_path)
    for plan in [
        models.TestPlan(commands=["go_test_all"], reason="wrong"),
        models.TestPlan(commands=["python_pytest"], targeted_paths=["../outside"], reason="escape"),
        models.TestPlan(commands=["python_pytest"], targeted_paths=["--help"], reason="option"),
    ]:
        with pytest.raises(ValueError):
            module.resolve_commands(profile, plan, tmp_path)


def test_empty_report_cannot_pass():
    models = next_module("agent.models")
    with pytest.raises(ValueError):
        models.TestReport(project_type="Python", results=[], all_required_passed=True)


@pytest.mark.parametrize(
    "kind,action",
    [
        ("implementation_error", "retry_coder"),
        ("wrong_plan", "replan"),
        ("test_selection_error", "rerun_tests"),
        ("dependency_error", "recover_environment"),
        ("environment_error", "stop"),
        ("unrecoverable", "stop"),
    ],
)
def test_diagnosis_actions(kind, action):
    models = next_module("agent.models")
    diagnosis = models.FailureDiagnosis(failure_type=kind, evidence=["test"], recommended_action=action, confidence=1)
    failure = next_module("agent.failure")
    assert failure.recovery_action(diagnosis, {}) == action
    if action != "stop":
        assert (
            failure.recovery_action(
                diagnosis, {"coder_retries": 99, "replans": 99, "test_replans": 99, "environment_recoveries": 99}
            )
            == "stop"
        )


def test_ablation_disables_replanning():
    models = next_module("agent.models")
    diagnosis = models.FailureDiagnosis(
        failure_type="wrong_plan", evidence=[], recommended_action="replan", confidence=1
    )
    assert next_module("agent.failure").recovery_action(diagnosis, {"ablation": "no_replanner"}) == "retry_coder"


def test_docker_resource_and_secret_boundary(tmp_path):
    backend = next_module("core.execution.docker").DockerSandboxBackend("example:test")
    cmd = backend.command(["python", "-m", "pytest"], tmp_path, "test-container")
    for flag in ["--memory", "--cpus", "--pids-limit", "--network", "--cap-drop", "--security-opt"]:
        assert flag in cmd
    assert "--privileged" not in cmd
    assert not any("docker.sock" in part or "API_KEY" in part for part in cmd)
    assert cmd.count("--mount") == 1
    assert "--log-driver" in cmd and "none" in cmd
    assert any("/workspace:rw" in part for part in cmd)


def test_executor_bounds_noisy_output(tmp_path):
    import sys

    execute = next_module("core.execution.local").execute
    result = execute([sys.executable, "-c", "print('x' * 1000000)"], tmp_path, 10)
    assert result.exit_code == 0
    assert len(result.stdout_summary) < 8500


def test_executor_timeout(tmp_path):
    import sys

    result = next_module("core.execution.local").execute(
        [sys.executable, "-c", "import time; time.sleep(30)"], tmp_path, 1
    )
    assert result.status == "timeout"


def test_missing_module_is_not_automatically_infrastructure():
    from agent.failure import deterministic_diagnosis
    from agent.models import TestCommandResult, TestReport

    report = TestReport(
        project_type="Python",
        all_required_passed=False,
        results=[
            TestCommandResult(
                command="python_pytest",
                exit_code=2,
                status="failed",
                stderr_summary="ModuleNotFoundError: No module named 'servcie'",
            )
        ],
    )
    assert deterministic_diagnosis(report) is None


def test_swebench_sandbox_uses_prepared_interpreter_and_path(tmp_path):
    from core.execution.docker import DockerSandboxBackend

    backend = DockerSandboxBackend(
        "swebench/instance:test",
        python_executable="/opt/miniconda3/envs/testbed/bin/python",
        container_workspace="/testbed",
    )
    command = backend.command(["python", "-m", "pytest"], tmp_path, "test")
    assert command[-3:] == ["/opt/miniconda3/envs/testbed/bin/python", "-m", "pytest"]
    assert command[command.index("--workdir") + 1] == "/testbed"
    assert "/testbed:rw,nosuid,size=512m,mode=1777" in command
    assert "PYTHONPATH=/testbed:/testbed/src" in command
