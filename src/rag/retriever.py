"""
src/rag/retriever.py
--------------------
混合检索器：向量（ChromaDB）+ BM25 + RRF 融合。

RRF: score(d) = Σ 1 / (k + rank_i(d))，k=60
"""

import fnmatch
import logging
import re
from typing import Optional

from rank_bm25 import BM25Okapi

from src.rag.chunker import CodeChunk
from src.rag.indexer import chunk_id

logger = logging.getLogger(__name__)

_RRF_K = 60


def _tokenize(text: str) -> list:
    return [t for t in re.split(r"[^a-zA-Z0-9_]", text.lower()) if t]


def _rrf_fuse(ranked_lists: list, k: int = _RRF_K) -> list:
    """RRF 融合多个排名列表，返回融合后降序 ID 列表。"""
    scores: dict = {}
    for ranked in ranked_lists:
        for rank, doc_id in enumerate(ranked):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank + 1)
    return sorted(scores, key=lambda x: scores[x], reverse=True)


class CodeRetriever:
    """
    混合检索器。

    Args:
        collection: ChromaDB collection（来自 CodeIndexer.get_collection()）
        chunks: 全量 CodeChunk 列表（用于 BM25 和结果映射）
        embedding_model: OpenAI embedding 模型名
        openai_client: openai.OpenAI 实例
    """

    def __init__(self, collection, chunks: list, embedding_model: str, openai_client):
        self._collection = collection
        self._chunks = chunks
        self._model = embedding_model
        self._openai = openai_client
        self._chunk_ids = [chunk_id(c) for c in chunks]
        self._id_to_chunk: dict = dict(zip(self._chunk_ids, chunks))

        if chunks:
            corpus = [_tokenize(c.code + " " + c.symbol_name) for c in chunks]
            self._bm25: Optional[BM25Okapi] = BM25Okapi(corpus)
        else:
            self._bm25 = None

        logger.info("retriever: 初始化完成，%d 个 chunk", len(chunks))

    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        file_pattern: Optional[str] = None,
    ) -> list:
        """
        混合检索，返回按相关度排序的 CodeChunk 列表。

        Args:
            query: 自然语言查询
            top_k: 返回结果数（最多 10）
            file_pattern: 可选 glob 文件路径过滤（例："auth/*.py"）
        """
        if not self._chunks:
            return []

        top_k = max(1, min(top_k, 10))
        n_candidates = min(top_k * 3, len(self._chunks))

        # ── 向量检索 ──
        vector_ids: list = []
        try:
            embedding = self._openai.embeddings.create(
                input=[query], model=self._model
            ).data[0].embedding
            result = self._collection.query(
                query_embeddings=[embedding],
                n_results=n_candidates,
                include=["metadatas"],
            )
            vector_ids = result["ids"][0] if result.get("ids") else []
        except Exception as e:
            logger.warning("retriever: 向量检索失败，降级 BM25: %s", e)

        # ── BM25 检索 ──
        bm25_ids: list = []
        if self._bm25 is not None:
            query_tokens = _tokenize(query)
            scores = self._bm25.get_scores(query_tokens)
            top_indices = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:n_candidates]
            bm25_ids = [self._chunk_ids[i] for i in top_indices]

        # ── RRF 融合 ──
        ranked_lists = [lst for lst in [vector_ids, bm25_ids] if lst]
        if not ranked_lists:
            return []

        fused = _rrf_fuse(ranked_lists)

        # ── 过滤 + 取 top_k ──
        results: list = []
        for cid in fused:
            chunk = self._id_to_chunk.get(cid)
            if chunk is None:
                continue
            if file_pattern and not fnmatch.fnmatch(chunk.file_path, file_pattern):
                continue
            results.append(chunk)
            if len(results) >= top_k:
                break

        logger.debug("retriever: '%s' → %d 个结果", query[:50], len(results))
        return results
