"""
tests/test_package_boundaries.py
--------------------------------
Import boundary tests for the public Python module layout.
"""

from core.rag import CodeChunk, CodeChunker, CodeIndexer, CodeRetriever
from tools.search_codebase_semantic import semantic_search_codebase


def test_rag_modules_are_importable_from_core_package():
    """RAG primitives should live under the core package boundary."""
    assert CodeChunk is not None
    assert CodeChunker is not None
    assert CodeIndexer is not None
    assert CodeRetriever is not None


def test_semantic_search_tool_is_importable_from_tools_package():
    """Agent tools should be importable from the top-level tools package."""
    assert semantic_search_codebase.name == "semantic_search_codebase"
