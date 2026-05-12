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
        # must sync to /testbed by default
        assert "autopatch_flask:/testbed/" in calls[0][2]

        # Second call must be docker exec
        assert calls[1][0] == "docker"
        assert calls[1][1] == "exec"
        assert "autopatch_flask" in calls[1]

    def test_custom_container_path(self):
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
                container_path="/repo",
                timeout=10,
            )

        assert "autopatch_flask:/repo/" in calls[0][2]

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
            if "cp" in cmd:
                m.returncode = 0
                m.stdout = ""
                m.stderr = ""
            else:
                m.returncode = 1
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
