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
    from core.task_store import TaskStore

    # Ensure task_store is initialised so the endpoint doesn't short-circuit with 503
    monkeypatch.setattr(server, "task_store", TaskStore(tasks_dir=tmp_path / "tasks"))

    random_id = str(uuid.uuid4())
    transport = httpx.ASGITransport(app=fastapi_app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        resp = await client.delete(f"/api/tasks/{random_id}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_auth_required_when_configured():
    """With AUTOPATCH_API_KEY set, POST /api/patch without token returns 401."""
    from api.auth import set_api_key_for_testing

    try:
        set_api_key_for_testing("test-secret-key-12345")

        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post("/api/patch", json={"repoUrl": "owner/repo", "issueNumber": 1})
        assert resp.status_code == 401
    finally:
        set_api_key_for_testing("")


@pytest.mark.asyncio
async def test_auth_passes_with_valid_token():
    """With AUTOPATCH_API_KEY set and valid Bearer token, request should not get 401.

    It may return other errors (e.g. 500 from missing agent_app), but NOT 401.
    """
    from api.auth import set_api_key_for_testing

    try:
        secret = "test-secret-key-12345"
        set_api_key_for_testing(secret)

        transport = httpx.ASGITransport(app=fastapi_app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            resp = await client.post(
                "/api/patch",
                json={"repoUrl": "owner/repo", "issueNumber": 1},
                headers={"Authorization": f"Bearer {secret}"},
            )
        assert resp.status_code != 401
    finally:
        set_api_key_for_testing("")


# ── POST /api/apply ─────────────────────────────────────────


class TestApplyEndpoint:
    @pytest.mark.asyncio
    async def test_apply_returns_pr_url(self, monkeypatch):
        import server
        from unittest.mock import MagicMock, patch

        # mock git_apply_and_push — 跳过真实 git/push
        monkeypatch.setattr(server, "git_apply_and_push", lambda *a, **kw: None)

        mock_client = MagicMock()
        mock_client.fetch_repo_metadata.return_value = {"default_branch": "main"}
        mock_client.create_pull_request.return_value = "https://github.com/owner/repo/pull/99"

        mock_ws = MagicMock()
        mock_ws.clone.return_value = "/tmp/fake_repo"

        with patch("server.GitHubClient", return_value=mock_client), \
             patch("server.RepoWorkspace", return_value=mock_ws):
            transport = httpx.ASGITransport(app=fastapi_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.post("/api/apply", json={
                    "repoUrl":     "owner/repo",
                    "issueNumber": 42,
                    "diffContent": "diff --git a/x b/x\n",
                })

        assert resp.status_code == 200
        data = resp.json()
        assert data["prUrl"] == "https://github.com/owner/repo/pull/99"
        assert data["branchName"] == "autopatch/issue-42"

    @pytest.mark.asyncio
    async def test_apply_github_error_returns_422(self, monkeypatch):
        import server
        import requests
        from unittest.mock import MagicMock, patch

        monkeypatch.setattr(server, "git_apply_and_push", lambda *a, **kw: None)

        mock_client = MagicMock()
        mock_client.fetch_repo_metadata.return_value = {"default_branch": "main"}
        mock_client.create_pull_request.side_effect = requests.HTTPError("403 Forbidden")

        mock_ws = MagicMock()
        mock_ws.clone.return_value = "/tmp/fake_repo"

        with patch("server.GitHubClient", return_value=mock_client), \
             patch("server.RepoWorkspace", return_value=mock_ws):
            transport = httpx.ASGITransport(app=fastapi_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.post("/api/apply", json={
                    "repoUrl":     "owner/repo",
                    "issueNumber": 42,
                    "diffContent": "diff --git a/x b/x\n",
                })

        assert resp.status_code == 422

    @pytest.mark.asyncio
    async def test_apply_clone_failure_cleans_up_workspace(self, monkeypatch):
        """clone 失败时 workspace 目录应被清理（不泄漏磁盘空间）。"""
        import server
        from unittest.mock import MagicMock, patch

        mock_ws = MagicMock()
        mock_ws.clone.side_effect = RuntimeError("clone failed")

        mock_client = MagicMock()
        mock_client.fetch_repo_metadata.return_value = {"default_branch": "main"}

        with patch("server.GitHubClient", return_value=mock_client), \
             patch("server.RepoWorkspace", return_value=mock_ws):
            transport = httpx.ASGITransport(app=fastapi_app)
            async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                resp = await client.post("/api/apply", json={
                    "repoUrl":     "owner/repo",
                    "issueNumber": 42,
                    "diffContent": "diff --git a/x b/x\n",
                })

        assert resp.status_code == 422
        mock_ws.cleanup.assert_called_once()
