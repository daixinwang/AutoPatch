"""
tests/test_task_store.py
------------------------
Tests for task_store.TaskStore CRUD operations and safety checks.
Uses tmp_path fixture for an isolated tasks directory -- no real DB needed.
"""

import tempfile
import uuid
from pathlib import Path

import pytest

from task_store import TaskStore


@pytest.fixture()
def store(tmp_path: Path) -> TaskStore:
    """Create a TaskStore backed by a temporary directory."""
    return TaskStore(tasks_dir=tmp_path / "tasks")


def _make_id() -> str:
    return str(uuid.uuid4())


# ── CRUD ────────────────────────────────────────────────────


class TestTaskStore:
    def test_create_and_get(self, store: TaskStore):
        tid = _make_id()
        rec = store.create(
            repo_url="owner/repo",
            issue_number=1,
            workspace_path="/tmp/ws",
            repo_language="Python",
            issue_text="Fix bug",
            task_id=tid,
        )
        assert rec.task_id == tid
        assert rec.status == "running"

        fetched = store.get(tid)
        assert fetched is not None
        assert fetched.task_id == tid
        assert fetched.repo_url == "owner/repo"
        assert fetched.issue_number == 1
        assert fetched.repo_language == "Python"
        assert fetched.issue_text == "Fix bug"

    def test_update_status(self, store: TaskStore):
        tid = _make_id()
        store.create(
            repo_url="owner/repo",
            issue_number=2,
            workspace_path="/tmp/ws2",
            repo_language="Go",
            issue_text="Add feature",
            task_id=tid,
        )
        store.update_status(tid, "completed")

        rec = store.get(tid)
        assert rec is not None
        assert rec.status == "completed"

    def test_delete_removes_record(self, store: TaskStore):
        tid = _make_id()
        store.create(
            repo_url="owner/repo",
            issue_number=3,
            workspace_path="/tmp/ws3",
            repo_language="Rust",
            issue_text="Refactor",
            task_id=tid,
        )
        deleted = store.delete(tid, remove_workspace=False)
        assert deleted is True
        assert store.get(tid) is None

    def test_list_all_descending(self, store: TaskStore):
        ids = []
        for i in range(3):
            tid = _make_id()
            ids.append(tid)
            store.create(
                repo_url="owner/repo",
                issue_number=i,
                workspace_path=f"/tmp/ws{i}",
                repo_language="Python",
                issue_text=f"Task {i}",
                task_id=tid,
            )

        records = store.list_all()
        assert len(records) == 3
        # created_at timestamps are monotonically increasing, so
        # descending order means the last-created record comes first.
        assert records[0].task_id == ids[-1]
        assert records[-1].task_id == ids[0]

    def test_invalid_task_id_rejected(self, store: TaskStore):
        with pytest.raises(ValueError):
            store.get("../../evil")

        with pytest.raises(ValueError):
            store.delete("../../evil")

    def test_delete_only_removes_tmp_workspace(self, store: TaskStore, tmp_path: Path, monkeypatch):
        """Workspace paths outside the system tempdir must NOT be deleted."""
        # Create a real directory with a sentinel file.
        outside_dir = tmp_path / "outside_workspace"
        outside_dir.mkdir()
        sentinel = outside_dir / "important.txt"
        sentinel.write_text("do not delete")

        # Patch tempfile.gettempdir so the code thinks the system temp dir
        # is somewhere else entirely.  This makes outside_dir fail the
        # is_relative_to check, exercising the safety guard.
        monkeypatch.setattr(tempfile, "gettempdir", lambda: "/faketemp")

        tid = _make_id()
        store.create(
            repo_url="owner/repo",
            issue_number=10,
            workspace_path=str(outside_dir),
            repo_language="Python",
            issue_text="Should not nuke workspace",
            task_id=tid,
        )

        store.delete(tid, remove_workspace=True)

        # The directory is "outside tempdir" (as far as the code knows),
        # so it must still exist.
        assert sentinel.exists(), "Workspace outside tempdir was incorrectly deleted"
