"""tests/test_rag_indexer.py"""
from unittest.mock import MagicMock

from src.rag.indexer import _embed_with_retry


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
