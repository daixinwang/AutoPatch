"""
tests/test_file_tools.py
------------------------
Tests for tools/file_tools.py (read_file, write_and_replace_file, edit_file).
"""

import pytest

from tools.file_tools import read_file, write_and_replace_file, edit_file


class TestReadFile:
    """read_file tool tests."""

    def test_read_file(self, tmp_workspace):
        target = tmp_workspace / "hello.txt"
        target.write_text("hello world", encoding="utf-8")

        result = read_file.invoke({"file_path": "hello.txt"})
        assert result == "hello world"

    def test_read_file_not_found(self, tmp_workspace):
        result = read_file.invoke({"file_path": "no_such_file.txt"})
        assert "错误" in result or "不存在" in result


class TestWriteAndReplaceFile:
    """write_and_replace_file tool tests."""

    def test_write_and_replace_file(self, tmp_workspace):
        result = write_and_replace_file.invoke(
            {"file_path": "output.txt", "content": "new content"}
        )
        assert "成功" in result
        assert (tmp_workspace / "output.txt").read_text(encoding="utf-8") == "new content"

    def test_write_creates_parent_dirs(self, tmp_workspace):
        result = write_and_replace_file.invoke(
            {"file_path": "deep/nested/dir/file.py", "content": "# code"}
        )
        assert "成功" in result
        assert (tmp_workspace / "deep" / "nested" / "dir" / "file.py").exists()

    def test_write_rejects_test_file(self, tmp_workspace):
        result = write_and_replace_file.invoke(
            {"file_path": "tests/test_foo.py", "content": "# forbidden"}
        )
        assert "拒绝" in result
        assert not (tmp_workspace / "tests" / "test_foo.py").exists()


class TestEditFile:
    """edit_file tool tests."""

    def test_edit_file_unique_match(self, tmp_workspace):
        target = tmp_workspace / "code.py"
        target.write_text("x = 1\ny = 2\nz = 3\n", encoding="utf-8")

        result = edit_file.invoke(
            {"file_path": "code.py", "old_string": "y = 2", "new_string": "y = 42"}
        )
        assert "成功" in result
        assert "y = 42" in target.read_text(encoding="utf-8")

    def test_edit_file_no_match(self, tmp_workspace):
        target = tmp_workspace / "code.py"
        target.write_text("x = 1\n", encoding="utf-8")

        result = edit_file.invoke(
            {"file_path": "code.py", "old_string": "not here", "new_string": "replacement"}
        )
        assert "错误" in result
        assert "预览" in result or "500" in result

    def test_edit_file_multiple_matches(self, tmp_workspace):
        target = tmp_workspace / "code.py"
        target.write_text("a = 1\na = 1\na = 1\n", encoding="utf-8")

        result = edit_file.invoke(
            {"file_path": "code.py", "old_string": "a = 1", "new_string": "a = 99"}
        )
        assert "错误" in result
        assert "3" in result
