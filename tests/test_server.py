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
