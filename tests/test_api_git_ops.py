"""
tests/test_api_git_ops.py
-------------------------
Unit tests for git apply/commit/push orchestration used by the apply endpoint.
"""

import pytest


class TestGitApplyAndPush:
    """Test git_apply_and_push while mocking the network push step."""

    def _make_repo_with_file(self, tmp_path):
        import subprocess

        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True, capture_output=True)
        hello = repo / "hello.py"
        hello.write_text("def hello():\n    return 'world'\n")
        subprocess.run(["git", "add", "."], cwd=repo, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True, capture_output=True)
        return repo

    def _make_diff(self, repo_path):
        import subprocess

        hello = repo_path / "hello.py"
        original = hello.read_text()
        hello.write_text(original + "\ndef bye():\n    return 'bye'\n")
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=repo_path, capture_output=True, text=True, check=True,
        )
        diff_content = result.stdout
        hello.write_text(original)
        subprocess.run(["git", "checkout", "--", "hello.py"], cwd=repo_path, check=True, capture_output=True)
        return diff_content

    def test_applies_diff_and_commits(self, tmp_path, monkeypatch):
        import subprocess
        from api.git_ops import git_apply_and_push
        from core.github_client import parse_github_url

        repo = self._make_repo_with_file(tmp_path)
        diff_content = self._make_diff(repo)
        repo_info = parse_github_url("owner/repo")

        push_calls = []
        real_run = subprocess.run

        def fake_run(cmd, **kwargs):
            if isinstance(cmd, list) and "push" in cmd:
                push_calls.append(cmd)
                return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            return real_run(cmd, **kwargs)

        monkeypatch.setattr(subprocess, "run", fake_run)

        git_apply_and_push(repo, "autopatch/issue-42", diff_content, repo_info, "fake-token")

        result = real_run(
            ["git", "branch", "--list", "autopatch/issue-42"],
            cwd=repo, capture_output=True, text=True,
        )
        assert "autopatch/issue-42" in result.stdout
        assert len(push_calls) == 1
        assert "push" in push_calls[0]

    def test_raises_on_invalid_diff(self, tmp_path, monkeypatch):
        import subprocess
        from api.git_ops import git_apply_and_push
        from core.github_client import parse_github_url

        repo = self._make_repo_with_file(tmp_path)
        repo_info = parse_github_url("owner/repo")

        real_run = subprocess.run

        def fake_run(cmd, **kwargs):
            if isinstance(cmd, list) and "push" in cmd:
                return type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
            return real_run(cmd, **kwargs)

        monkeypatch.setattr(subprocess, "run", fake_run)

        with pytest.raises(subprocess.CalledProcessError):
            git_apply_and_push(
                repo, "autopatch/issue-99",
                "this is not a valid diff at all",
                repo_info, "fake-token",
            )
