"""
src/rag/indexer.py
------------------
ChromaDB 向量索引构建器。

存储路径：{RAG_CACHE_DIR}/rag_index/{repo_hash}/
增量更新：基于 chunk_id 是否已存在，只对新增 chunk 调用 Embedding API。
"""

import hashlib
import logging
import time
from pathlib import Path
from typing import Optional

import chromadb
from chromadb.config import Settings

from src.rag.chunker import CodeChunk
from core.config import (
    RAG_CACHE_DIR,
    RAG_EMBEDDING_MODEL,
    RAG_EMBEDDING_DIMENSIONS,
    OPENAI_EMBED_API_KEY,
    OPENAI_EMBED_BASE_URL,
)

logger = logging.getLogger(__name__)

_COLLECTION_NAME = "code_chunks"
_BATCH_SIZE = 100  # 每批 embed 的 chunk 数


def _repo_hash(repo_path: str) -> str:
    """基于仓库绝对路径生成 16 字符 hex 标识。"""
    return hashlib.sha256(str(Path(repo_path).resolve()).encode()).hexdigest()[:16]


def chunk_id(chunk: CodeChunk) -> str:
    """为 chunk 生成稳定 ID（MD5 前 16 位）。"""
    key = f"{chunk.file_path}::{chunk.symbol_name}::{chunk.start_line}"
    return hashlib.md5(key.encode()).hexdigest()[:16]


def _embed_with_retry(
    client,
    texts: list[str],
    model: str,
    dimensions: int = 0,
    max_retries: int = 3,
) -> list[list[float]]:
    """调用 OpenAI Embedding API，失败时指数退避重试。"""
    for attempt in range(max_retries):
        try:
            kwargs = {"input": texts, "model": model}
            if dimensions > 0:
                kwargs["dimensions"] = dimensions
            response = client.embeddings.create(**kwargs)
            return [item.embedding for item in response.data]
        except Exception as e:
            wait = 2 ** attempt
            if attempt < max_retries - 1:
                logger.warning(
                    "indexer: embedding API 失败（%d/%d），%ds 后重试: %s",
                    attempt + 1, max_retries, wait, e,
                )
                time.sleep(wait)
            else:
                raise RuntimeError(f"embedding API 在 {max_retries} 次重试后仍失败: {e}") from e


class CodeIndexer:
    """构建并维护 ChromaDB 向量索引。"""

    def __init__(self, repo_path: str, cache_dir: Optional[str] = None):
        self.repo_path = str(Path(repo_path).resolve())
        index_dir = Path(cache_dir or RAG_CACHE_DIR) / "rag_index" / _repo_hash(self.repo_path)
        index_dir.mkdir(parents=True, exist_ok=True)
        self._index_dir = index_dir

        self._chroma = chromadb.PersistentClient(
            path=str(index_dir),
            settings=Settings(anonymized_telemetry=False),
        )
        self._collection = self._chroma.get_or_create_collection(
            name=_COLLECTION_NAME,
            metadata={"hnsw:space": "cosine"},
        )

        import openai
        self._openai = openai.OpenAI(
            api_key=OPENAI_EMBED_API_KEY or None,
            base_url=OPENAI_EMBED_BASE_URL or None,
        )
        self._model = RAG_EMBEDDING_MODEL
        self._dimensions = RAG_EMBEDDING_DIMENSIONS

    def build_or_update(self, chunks: list[CodeChunk]) -> int:
        """
        增量更新索引，返回新写入的 chunk 数。
        仅对 ID 不在集合中的 chunk 调用 Embedding API。
        """
        if not chunks:
            logger.info("indexer: 没有 chunk 需要索引")
            return 0

        try:
            existing_ids: set[str] = set(self._collection.get(include=[])["ids"])
        except Exception:
            existing_ids = set()

        new_pairs = [(chunk_id(c), c) for c in chunks if chunk_id(c) not in existing_ids]

        if not new_pairs:
            logger.info("indexer: 索引已是最新（%d 个 chunk 无变更）", len(chunks))
            return 0

        logger.info("indexer: 新增 %d 个 chunk（共 %d 个）", len(new_pairs), len(chunks))
        total = 0
        for i in range(0, len(new_pairs), _BATCH_SIZE):
            batch = new_pairs[i: i + _BATCH_SIZE]
            ids = [cid for cid, _ in batch]
            texts = [_chunk_to_text(c) for _, c in batch]
            metadatas = [_chunk_to_metadata(c) for _, c in batch]
            documents = [c.code for _, c in batch]
            try:
                embeddings = _embed_with_retry(
                    self._openai,
                    texts,
                    self._model,
                    dimensions=self._dimensions,
                )
                self._collection.upsert(
                    ids=ids, embeddings=embeddings,
                    documents=documents, metadatas=metadatas,
                )
                total += len(batch)
            except Exception as e:
                logger.error("indexer: 批次 %d 写入失败，跳过: %s", i, e)

        logger.info("indexer: 完成，共写入 %d 个 chunk", total)
        return total

    def get_collection(self):
        """返回 ChromaDB collection，供 CodeRetriever 使用。"""
        return self._collection


def _chunk_to_text(chunk: CodeChunk) -> str:
    parts = [f"File: {chunk.file_path}", f"Symbol: {chunk.symbol_name} ({chunk.symbol_type})"]
    if chunk.parent_class:
        parts.append(f"Class: {chunk.parent_class}")
    if chunk.docstring:
        parts.append(f"Docstring: {chunk.docstring}")
    parts.append(chunk.code)
    return "\n".join(parts)


def _chunk_to_metadata(chunk: CodeChunk) -> dict:
    return {
        "file_path": chunk.file_path,
        "symbol_name": chunk.symbol_name,
        "symbol_type": chunk.symbol_type,
        "start_line": chunk.start_line,
        "end_line": chunk.end_line,
        "parent_class": chunk.parent_class or "",
        "is_oversized": chunk.is_oversized,
        "has_docstring": chunk.docstring is not None,
    }
