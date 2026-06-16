"""
tests/test_api_diff_service.py
------------------------------
Unit tests for diff generation and persistence used by API pipelines.
"""

from pathlib import Path

import pytest

from api.diff_service import generate_and_save_diff


@pytest.mark.asyncio
async def test_generate_and_save_diff_returns_diff_and_changed_paths(monkeypatch):
    writes = []

    def fake_generate_diff(tmp_dir):
        assert tmp_dir == "/tmp/repo"
        return "diff --git a/a.py b/a.py\n"

    def fake_get_changed_files(tmp_dir):
        assert tmp_dir == "/tmp/repo"
        return [{"path": "a.py"}, {"path": "b.py"}]

    def fake_write_diff_file(diff_content, diff_path, repo_url, issue_number, review_result):
        writes.append((diff_content, diff_path, repo_url, issue_number, review_result))

    monkeypatch.setattr("api.diff_service.generate_diff", fake_generate_diff)
    monkeypatch.setattr("api.diff_service.get_changed_files", fake_get_changed_files)
    monkeypatch.setattr("api.diff_service.write_diff_file", fake_write_diff_file)

    diff_content, changed_files = await generate_and_save_diff(
        "/tmp/repo",
        issue_number=42,
        repo_url="owner/repo",
        review_result="PASS",
    )

    assert diff_content == "diff --git a/a.py b/a.py\n"
    assert changed_files == ["a.py", "b.py"]
    assert len(writes) == 1
    written_diff, diff_path, repo_url, issue_number, review_result = writes[0]
    assert written_diff == diff_content
    assert Path(diff_path).parent == Path("patches")
    assert Path(diff_path).name.startswith("issue-42_")
    assert repo_url == "owner/repo"
    assert issue_number == 42
    assert review_result == "PASS"


@pytest.mark.asyncio
async def test_generate_and_save_diff_skips_write_when_diff_generation_fails(monkeypatch):
    writes = []

    def fake_generate_diff(tmp_dir):
        raise RuntimeError("no diff")

    def fake_get_changed_files(tmp_dir):
        return [{"path": "a.py"}]

    monkeypatch.setattr("api.diff_service.generate_diff", fake_generate_diff)
    monkeypatch.setattr("api.diff_service.get_changed_files", fake_get_changed_files)
    monkeypatch.setattr("api.diff_service.write_diff_file", lambda *args: writes.append(args))

    diff_content, changed_files = await generate_and_save_diff(
        "/tmp/repo",
        issue_number=7,
        repo_url="owner/repo",
        review_result="REJECT",
    )

    assert diff_content == ""
    assert changed_files == ["a.py"]
    assert writes == []
