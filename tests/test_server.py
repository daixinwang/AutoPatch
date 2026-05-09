"""
tests/test_server.py
--------------------
FastAPI server endpoint tests using httpx.AsyncClient with ASGITransport.
"""

import uuid

import httpx
import pytest

from server import fastapi_app


@pytest.mark.asyncio
async def test_health_endpoint():
    """GET /api/health returns 200 with {"status": "ok"}."""
    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_list_tasks_empty():
    """GET /api/tasks returns {"tasks": []} when task_store is None."""
    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.get("/api/tasks")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"tasks": []}


@pytest.mark.asyncio
async def test_delete_nonexistent_task(monkeypatch, tmp_path):
    """DELETE /api/tasks/{random-uuid} returns 404 for a task that does not exist."""
    import server
    from task_store import TaskStore

    # Ensure task_store is initialised so the endpoint doesn't short-circuit with 503
    monkeypatch.setattr(server, "task_store", TaskStore(tasks_dir=tmp_path / "tasks"))

    random_id = str(uuid.uuid4())
    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.delete(f"/api/tasks/{random_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_auth_required_when_configured(monkeypatch):
    """With AUTOPATCH_API_KEY set, POST /api/patch without token returns 401."""
    import server

    # Patch the module-level _API_KEY that _verify_api_key reads at runtime
    monkeypatch.setattr(server, "_API_KEY", "test-secret-key-12345")

    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post("/api/patch", json={"repoUrl": "owner/repo", "issueNumber": 1})
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_auth_passes_with_valid_token(monkeypatch):
    """With AUTOPATCH_API_KEY set and valid Bearer token, request should not get 401.

    It may return other errors (e.g. 500 from missing agent_app), but NOT 401.
    """
    import server

    secret = "test-secret-key-12345"
    monkeypatch.setattr(server, "_API_KEY", secret)

    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.post(
            "/api/patch",
            json={"repoUrl": "owner/repo", "issueNumber": 1},
            headers={"Authorization": f"Bearer {secret}"},
        )
    assert resp.status_code != 401


# ── _git_apply_and_push ────────────────────────────────────


class TestGitApplyAndPush:
    """测试 _git_apply_and_push 的 git 操作（mock push 步骤）。"""

    def _make_repo_with_file(self, tmp_path):
        """创建一个带初始 commit 的本地 git 仓库，包含 hello.py。"""
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
        """在 repo 中添加一行后生成 diff，再还原，用于测试 apply。"""
        import subprocess
        hello = repo_path / "hello.py"
        original = hello.read_text()
        hello.write_text(original + "\ndef bye():\n    return 'bye'\n")
        result = subprocess.run(
            ["git", "diff", "HEAD"],
            cwd=repo_path, capture_output=True, text=True, check=True,
        )
        diff_content = result.stdout
        # 还原文件，让 apply 来应用
        hello.write_text(original)
        subprocess.run(["git", "checkout", "--", "hello.py"], cwd=repo_path, check=True, capture_output=True)
        return diff_content

    def test_applies_diff_and_commits(self, tmp_path, monkeypatch):
        import subprocess
        from github_client import parse_github_url
        from server import _git_apply_and_push

        repo = self._make_repo_with_file(tmp_path)
        diff_content = self._make_diff(repo)

        repo_info = parse_github_url("owner/repo")

        # mock push — 不实际推送到 GitHub
        push_calls = []
        real_run = subprocess.run

        def fake_run(cmd, **kwargs):
            if isinstance(cmd, list) and "push" in cmd:
                push_calls.append(cmd)
                mock = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
                return mock
            return real_run(cmd, **kwargs)

        monkeypatch.setattr(subprocess, "run", fake_run)

        _git_apply_and_push(repo, "autopatch/issue-42", diff_content, repo_info, "fake-token")

        # 验证分支已创建
        result = real_run(
            ["git", "branch", "--list", "autopatch/issue-42"],
            cwd=repo, capture_output=True, text=True,
        )
        assert "autopatch/issue-42" in result.stdout

        # 验证 push 被调用
        assert len(push_calls) == 1
        assert "push" in push_calls[0]
