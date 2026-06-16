"""
tools/search_codebase_semantic.py
---------------------------------
语义代码搜索 LangChain 工具（@tool 装饰器封装）。
工具名：semantic_search_codebase
"""

import logging
from typing import Optional

from langchain_core.tools import tool

from tools.workspace import get_retriever

logger = logging.getLogger(__name__)


@tool
def semantic_search_codebase(
    query: str,
    top_k: int = 5,
    file_pattern: Optional[str] = None,
) -> str:
    """
    Semantically search the codebase using vector embeddings + BM25 hybrid retrieval.

    Use this tool when:
    - You need to find code by concept or description (e.g., "authentication logic", "database connection pool")
    - The exact function or variable name is unknown
    - search_codebase (grep) returns too many noisy results

    Do NOT use this as a replacement for search_codebase when you already know the exact
    identifier name — grep is faster and more precise for exact matches.

    Args:
        query:        Natural language description of the code you are looking for.
                      Example: "function that validates JWT tokens"
        top_k:        Number of results to return (1-10, default 5).
        file_pattern: Optional glob pattern to filter results by file path.
                      Example: "auth/*.py" or "*/models.py"

    Returns:
        Formatted code chunks with file path, line numbers, symbol name, and code content.
        If RAG is unavailable (non-Python repo or indexing failed), returns a fallback message.
    """
    try:
        retriever = get_retriever()
        if retriever is None:
            return (
                "[semantic_search_codebase] RAG index is not available for this repository "
                "(non-Python repo, indexing failed, or OPENAI_EMBED_API_KEY not set). "
                "Please use search_codebase or find_definition instead."
            )

        top_k = max(1, min(int(top_k), 10))
        chunks = retriever.retrieve(query=query, top_k=top_k, file_pattern=file_pattern)

        if not chunks:
            return f"[semantic_search_codebase] No semantically relevant code found for: {query!r}"

        lines = [f"[semantic_search_codebase] Found {len(chunks)} relevant chunks:\n"]
        for i, chunk in enumerate(chunks, 1):
            header = (
                f"--- [{i}] {chunk.file_path}:{chunk.start_line}-{chunk.end_line}"
                f" ({chunk.symbol_type}: {chunk.symbol_name})"
            )
            if chunk.parent_class:
                header += f" [in class {chunk.parent_class}]"
            lines.append(header)
            if chunk.docstring:
                lines.append(f"    # {chunk.docstring[:200]}")
            code_preview = chunk.code[:800]
            if len(chunk.code) > 800:
                code_preview += "\n    ... (truncated, use read_file for full content)"
            lines.append(code_preview)
            lines.append("")

        return "\n".join(lines)

    except Exception as e:
        msg = f"[semantic_search_codebase] ERROR: {type(e).__name__}: {e}"
        logger.error(msg)
        return msg
