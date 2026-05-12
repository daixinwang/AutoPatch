"""
tests/test_execute_tools.py
---------------------------
Tests for tools/execute_tools.py (verify_importable).
"""
import pytest

from tools.execute_tools import verify_importable


class TestVerifyImportable:
    """verify_importable tool tests."""

    def test_valid_module(self, tmp_workspace):
        (tmp_workspace / "mymod.py").write_text("x = 1\n", encoding="utf-8")
        result = verify_importable.invoke({"file_path": "mymod.py"})
        assert "成功" in result
        assert "mymod" in result

    def test_syntax_error(self, tmp_workspace):
        (tmp_workspace / "broken.py").write_text("def foo(\n", encoding="utf-8")
        result = verify_importable.invoke({"file_path": "broken.py"})
        assert "失败" in result or "错误" in result

    def test_import_error(self, tmp_workspace):
        (tmp_workspace / "bad_import.py").write_text(
            "import nonexistent_pkg_xyz\n", encoding="utf-8"
        )
        result = verify_importable.invoke({"file_path": "bad_import.py"})
        assert "失败" in result or "错误" in result

    def test_file_not_found(self, tmp_workspace):
        result = verify_importable.invoke({"file_path": "no_such_file.py"})
        assert "错误" in result or "不存在" in result

    def test_non_py_file(self, tmp_workspace):
        (tmp_workspace / "readme.txt").write_text("hello", encoding="utf-8")
        result = verify_importable.invoke({"file_path": "readme.txt"})
        assert "错误" in result

    def test_nested_module(self, tmp_workspace):
        pkg = tmp_workspace / "mypkg"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        (pkg / "utils.py").write_text("def helper(): return 42\n", encoding="utf-8")
        result = verify_importable.invoke({"file_path": "mypkg/utils.py"})
        assert "成功" in result
        assert "mypkg.utils" in result
