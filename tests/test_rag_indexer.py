"""tests/test_rag_indexer.py"""
from unittest.mock import MagicMock

from core.rag.chunker import CodeChunk
from core.rag.indexer import CodeIndexer, _chunk_to_text, _embed_with_retry


def test_embed_with_retry_passes_embedding_dimensions():
    client = MagicMock()
    item = MagicMock()
    item.embedding = [0.1, 0.2, 0.3]
    response = MagicMock()
    response.data = [item]
    client.embeddings.create.return_value = response

    result = _embed_with_retry(
        client,
        texts=["hello"],
        model="text-embedding-v4",
        dimensions=1024,
    )

    assert result == [[0.1, 0.2, 0.3]]
    client.embeddings.create.assert_called_once_with(
        input=["hello"],
        model="text-embedding-v4",
        dimensions=1024,
    )


def test_indexer_batches_embeddings_at_provider_limit(monkeypatch, tmp_path):
    embed_batch_sizes = []
    upsert_batch_sizes = []

    class FakeCollection:
        def get(self, include):
            return {"ids": []}

        def upsert(self, ids, embeddings, documents, metadatas):
            upsert_batch_sizes.append(len(ids))

    def fake_embed(client, texts, model, dimensions=0):
        embed_batch_sizes.append(len(texts))
        return [[0.0, 0.1, 0.2] for _ in texts]

    monkeypatch.setattr(CodeIndexer, "__init__", lambda self, repo_path, cache_dir=None: None)
    monkeypatch.setattr("core.rag.indexer._embed_with_retry", fake_embed)

    indexer = CodeIndexer(str(tmp_path))
    indexer._collection = FakeCollection()
    indexer._openai = object()
    indexer._model = "text-embedding-v4"
    indexer._dimensions = 1024

    chunks = [
        CodeChunk(
            file_path=f"module_{i}.py",
            symbol_name=f"function_{i}",
            symbol_type="function",
            start_line=i + 1,
            end_line=i + 1,
            code=f"def function_{i}():\n    return {i}",
        )
        for i in range(25)
    ]

    total = indexer.build_or_update(chunks)

    assert total == 25
    assert embed_batch_sizes == [10, 10, 5]
    assert upsert_batch_sizes == [10, 10, 5]


def test_chunk_to_text_caps_embedding_input_length():
    chunk = CodeChunk(
        file_path="huge_module.py",
        symbol_name="huge_function",
        symbol_type="function",
        start_line=1,
        end_line=9000,
        code="x" * 9000,
        docstring="doc",
    )

    text = _chunk_to_text(chunk)

    assert len(text) <= 8192
    assert text.startswith("File: huge_module.py\nSymbol: huge_function (function)")
