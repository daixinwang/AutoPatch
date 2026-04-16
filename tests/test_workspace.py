"""
tests/test_workspace.py
-----------------------
Tests for tools/workspace.py path-resolution and traversal prevention.
"""

import pytest

from tools.workspace import resolve_workspace_path, set_workspace, reset_workspace


class TestResolveWorkspacePath:
    """resolve_workspace_path security and correctness tests."""

    def test_resolve_relative_path(self, tmp_workspace):
        result = resolve_workspace_path("calc.py")
        assert result == tmp_workspace / "calc.py"

    def test_resolve_subdirectory(self, tmp_workspace):
        result = resolve_workspace_path("src/main.py")
        assert result == tmp_workspace / "src" / "main.py"

    def test_reject_absolute_path(self, tmp_workspace):
        with pytest.raises(ValueError):
            resolve_workspace_path("/etc/passwd")

    def test_reject_traversal(self, tmp_workspace):
        with pytest.raises(ValueError):
            resolve_workspace_path("../../etc/passwd")

    def test_reject_nested_traversal(self, tmp_workspace):
        with pytest.raises(ValueError):
            resolve_workspace_path("src/../../etc/passwd")

    def test_context_isolation(self, tmp_path):
        """Two set_workspace calls with different paths give independent results."""
        dir_a = tmp_path / "workspace_a"
        dir_b = tmp_path / "workspace_b"
        dir_a.mkdir()
        dir_b.mkdir()

        token_a = set_workspace(str(dir_a))
        try:
            result_a = resolve_workspace_path("file.txt")
            assert result_a == dir_a / "file.txt"
        finally:
            reset_workspace(token_a)

        token_b = set_workspace(str(dir_b))
        try:
            result_b = resolve_workspace_path("file.txt")
            assert result_b == dir_b / "file.txt"
        finally:
            reset_workspace(token_b)

        assert result_a != result_b
