"""
src/rag/chunker.py
------------------
AST 级 Python 代码切分器。

将 .py 文件解析为 CodeChunk 列表，粒度为函数/类/方法/模块级代码。
"""

import ast
import logging
from pathlib import Path
from typing import Literal, Optional

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_OVERSIZED_THRESHOLD = 300  # 超过此行数标记 is_oversized

_SKIP_DIRS = frozenset({
    ".git", ".venv", "venv", "__pycache__", "node_modules",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".tox",
})


class CodeChunk(BaseModel):
    file_path: str
    symbol_name: str
    symbol_type: Literal["function", "class", "method", "module"]
    start_line: int
    end_line: int
    code: str
    docstring: Optional[str] = None
    parent_class: Optional[str] = None
    is_oversized: bool = False


class CodeChunker:
    """将单个 .py 文件或整个目录切分为 CodeChunk 列表。"""

    def chunk_file(self, file_path: Path, repo_root: Path) -> list[CodeChunk]:
        """切分单个文件，出错返回空列表（不抛出异常）。"""
        try:
            source = file_path.read_text(encoding="utf-8", errors="ignore")
            rel_path = str(file_path.relative_to(repo_root))
            return self._parse(source, rel_path)
        except Exception as e:
            logger.warning("chunker: 跳过 %s: %s", file_path, e)
            return []

    def chunk_directory(self, repo_root: Path) -> list[CodeChunk]:
        """递归切分目录内所有 .py 文件，自动跳过 .venv 等目录。"""
        chunks: list[CodeChunk] = []
        for py_file in sorted(repo_root.rglob("*.py")):
            if any(part in _SKIP_DIRS for part in py_file.parts):
                continue
            chunks.extend(self.chunk_file(py_file, repo_root))
        logger.info("chunker: %s 共切分出 %d 个 chunk", repo_root, len(chunks))
        return chunks

    def _parse(self, source: str, rel_path: str) -> list[CodeChunk]:
        try:
            tree = ast.parse(source)
        except SyntaxError as e:
            logger.warning("chunker: 语法错误 %s: %s", rel_path, e)
            return []

        source_lines = source.splitlines()
        chunks: list[CodeChunk] = []

        module_chunk = self._extract_module_level(source_lines, tree, rel_path)
        if module_chunk:
            chunks.append(module_chunk)

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                chunks.append(self._make_chunk(node, source_lines, rel_path, "function"))
            elif isinstance(node, ast.ClassDef):
                chunks.append(self._make_chunk(node, source_lines, rel_path, "class"))
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        chunks.append(
                            self._make_chunk(child, source_lines, rel_path, "method",
                                             parent_class=node.name)
                        )
        return chunks

    def _make_chunk(
        self,
        node: ast.AST,
        source_lines: list[str],
        file_path: str,
        symbol_type: str,
        parent_class: Optional[str] = None,
    ) -> CodeChunk:
        start = node.lineno
        end = node.end_lineno
        if hasattr(node, "decorator_list") and node.decorator_list:
            start = node.decorator_list[0].lineno
        code = "\n".join(source_lines[start - 1: end])
        return CodeChunk(
            file_path=file_path,
            symbol_name=node.name,
            symbol_type=symbol_type,
            start_line=start,
            end_line=end,
            code=code,
            docstring=ast.get_docstring(node),
            parent_class=parent_class,
            is_oversized=(end - start + 1) > _OVERSIZED_THRESHOLD,
        )

    def _extract_module_level(
        self, source_lines: list[str], tree: ast.Module, file_path: str
    ) -> Optional[CodeChunk]:
        top_defs = [
            n for n in ast.iter_child_nodes(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
        ]
        cutoff = (min(n.lineno for n in top_defs) - 1) if top_defs else len(source_lines)
        if cutoff <= 0:
            return None
        module_code = "\n".join(source_lines[:cutoff]).strip()
        if not module_code:
            return None
        return CodeChunk(
            file_path=file_path,
            symbol_name="module",
            symbol_type="module",
            start_line=1,
            end_line=cutoff,
            code=module_code,
            docstring=ast.get_docstring(tree),
        )
