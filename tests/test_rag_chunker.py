"""tests/test_rag_chunker.py"""
import textwrap
from pathlib import Path

import pytest

from src.rag.chunker import CodeChunk, CodeChunker


@pytest.fixture
def chunker():
    return CodeChunker()


def write_py(tmp_path: Path, name: str, source: str) -> Path:
    f = tmp_path / name
    f.write_text(textwrap.dedent(source))
    return f


# ── 基本函数切分 ──────────────────────────────────────────────

def test_chunk_simple_function(tmp_path, chunker):
    write_py(tmp_path, "foo.py", """
        def greet(name: str) -> str:
            return f"Hello, {name}"
    """)
    chunks = chunker.chunk_directory(tmp_path)
    funcs = [c for c in chunks if c.symbol_type == "function"]
    assert len(funcs) == 1
    assert funcs[0].symbol_name == "greet"
    assert "def greet" in funcs[0].code


def test_chunk_with_decorator(tmp_path, chunker):
    write_py(tmp_path, "foo.py", """
        import functools

        @functools.lru_cache(maxsize=None)
        def expensive():
            return 42
    """)
    chunks = chunker.chunk_directory(tmp_path)
    funcs = [c for c in chunks if c.symbol_type == "function"]
    assert len(funcs) == 1
    assert "@functools.lru_cache" in funcs[0].code
    assert funcs[0].start_line < funcs[0].end_line


# ── 类 + 方法切分 ──────────────────────────────────────────────

def test_chunk_class_with_methods(tmp_path, chunker):
    write_py(tmp_path, "cls.py", """
        class Foo:
            def bar(self):
                pass

            def baz(self):
                pass
    """)
    chunks = chunker.chunk_directory(tmp_path)
    class_chunks = [c for c in chunks if c.symbol_type == "class"]
    method_chunks = [c for c in chunks if c.symbol_type == "method"]
    assert len(class_chunks) == 1
    assert class_chunks[0].symbol_name == "Foo"
    assert len(method_chunks) == 2
    assert all(c.parent_class == "Foo" for c in method_chunks)
    assert {c.symbol_name for c in method_chunks} == {"bar", "baz"}


# ── module chunk ───────────────────────────────────────────────

def test_module_chunk_contains_imports(tmp_path, chunker):
    write_py(tmp_path, "imports_only.py", """
        import os
        import sys
        CONST = 42

        def foo():
            pass
    """)
    chunks = chunker.chunk_directory(tmp_path)
    module_chunks = [c for c in chunks if c.symbol_type == "module"]
    assert len(module_chunks) == 1
    assert "import os" in module_chunks[0].code
    assert "CONST = 42" in module_chunks[0].code


def test_empty_file_no_module_chunk(tmp_path, chunker):
    write_py(tmp_path, "empty.py", "")
    chunks = chunker.chunk_directory(tmp_path)
    assert chunks == []


# ── oversized 标记 ─────────────────────────────────────────────

def test_oversized_flag(tmp_path, chunker):
    body = "\n".join(f"    x{i} = {i}" for i in range(310))
    source = f"def big_func():\n{body}\n    return x0\n"
    write_py(tmp_path, "big.py", source)
    chunks = chunker.chunk_directory(tmp_path)
    funcs = [c for c in chunks if c.symbol_type == "function"]
    assert funcs[0].is_oversized is True


def test_normal_function_not_oversized(tmp_path, chunker):
    write_py(tmp_path, "small.py", """
        def small():
            return 1
    """)
    chunks = chunker.chunk_directory(tmp_path)
    funcs = [c for c in chunks if c.symbol_type == "function"]
    assert funcs[0].is_oversized is False


# ── 错误处理 ───────────────────────────────────────────────────

def test_syntax_error_returns_empty(tmp_path, chunker):
    bad = tmp_path / "bad.py"
    bad.write_text("def broken(:\n    pass\n")
    chunks = chunker.chunk_file(bad, tmp_path)
    assert chunks == []


def test_chunk_directory_skips_venv(tmp_path, chunker):
    venv_dir = tmp_path / ".venv" / "lib"
    venv_dir.mkdir(parents=True)
    (venv_dir / "should_skip.py").write_text("def hidden(): pass\n")
    (tmp_path / "real.py").write_text("def visible(): pass\n")
    chunks = chunker.chunk_directory(tmp_path)
    names = [c.symbol_name for c in chunks if c.symbol_type == "function"]
    assert "visible" in names
    assert "hidden" not in names


# ── docstring 提取 ─────────────────────────────────────────────

def test_docstring_extracted(tmp_path, chunker):
    write_py(tmp_path, "doc.py", '''
        def documented():
            """This is the docstring."""
            pass
    ''')
    chunks = chunker.chunk_directory(tmp_path)
    funcs = [c for c in chunks if c.symbol_type == "function"]
    assert funcs[0].docstring == "This is the docstring."
