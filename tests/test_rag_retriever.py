"""tests/test_rag_retriever.py"""
import pytest
from unittest.mock import MagicMock

from src.rag.chunker import CodeChunk
from src.rag.retriever import CodeRetriever, _rrf_fuse, _tokenize


# ── 工具函数单元测试 ───────────────────────────────────────────

def test_rrf_fuse_single_list():
    result = _rrf_fuse([["a", "b", "c"]])
    assert result[0] == "a"
    assert result[-1] == "c"


def test_rrf_fuse_intersection_ranked_higher():
    list1 = ["a", "b", "c"]
    list2 = ["b", "d", "e"]
    result = _rrf_fuse([list1, list2])
    assert result[0] == "b"


def test_rrf_fuse_empty_lists():
    assert _rrf_fuse([]) == []
    assert _rrf_fuse([[]]) == []


def test_tokenize_code():
    tokens = _tokenize("def authenticate_user(username, password):")
    assert "def" in tokens
    assert "authenticate_user" in tokens
    assert "username" in tokens


# ── CodeRetriever 单元测试（mock Embedding API）──────────────

@pytest.fixture
def sample_chunks():
    return [
        CodeChunk(
            file_path="auth/login.py",
            symbol_name="authenticate_user",
            symbol_type="function",
            start_line=10, end_line=25,
            code="def authenticate_user(username, password):\n    pass",
            docstring="Authenticate user with username and password.",
        ),
        CodeChunk(
            file_path="utils/hash.py",
            symbol_name="hash_password",
            symbol_type="function",
            start_line=1, end_line=8,
            code="def hash_password(password: str) -> str:\n    return hashlib.sha256(password.encode()).hexdigest()",
        ),
        CodeChunk(
            file_path="models/user.py",
            symbol_name="User",
            symbol_type="class",
            start_line=1, end_line=30,
            code="class User:\n    def __init__(self, username): ...",
        ),
    ]


@pytest.fixture
def mock_collection(sample_chunks):
    from src.rag.indexer import chunk_id
    coll = MagicMock()
    coll.query.return_value = {
        "ids": [[chunk_id(sample_chunks[0])]],
        "metadatas": [[{"file_path": sample_chunks[0].file_path}]],
    }
    return coll


@pytest.fixture
def mock_openai_client():
    import numpy as np
    client = MagicMock()
    fake_embedding = MagicMock()
    fake_embedding.embedding = list(np.random.rand(1536))
    response = MagicMock()
    response.data = [fake_embedding]
    client.embeddings.create.return_value = response
    return client


def make_retriever(collection, chunks, openai_client):
    return CodeRetriever(
        collection=collection,
        chunks=chunks,
        embedding_model="text-embedding-3-small",
        openai_client=openai_client,
    )


def test_retrieve_returns_results(sample_chunks, mock_collection, mock_openai_client):
    retriever = make_retriever(mock_collection, sample_chunks, mock_openai_client)
    results = retriever.retrieve("authenticate user login", top_k=2)
    assert isinstance(results, list)
    assert len(results) <= 2


def test_retrieve_at_most_top_k(sample_chunks, mock_collection, mock_openai_client):
    retriever = make_retriever(mock_collection, sample_chunks, mock_openai_client)
    results = retriever.retrieve("some query", top_k=1)
    assert len(results) <= 1


def test_retrieve_fallback_to_bm25_on_vector_error(sample_chunks, mock_openai_client):
    broken_collection = MagicMock()
    broken_collection.query.side_effect = RuntimeError("API down")
    retriever = make_retriever(broken_collection, sample_chunks, mock_openai_client)
    results = retriever.retrieve("hash password security", top_k=3)
    assert isinstance(results, list)


def test_retrieve_with_file_pattern(sample_chunks, mock_collection, mock_openai_client):
    retriever = make_retriever(mock_collection, sample_chunks, mock_openai_client)
    results = retriever.retrieve("user", top_k=5, file_pattern="models/*.py")
    for chunk in results:
        assert chunk.file_path.startswith("models/")


def test_retrieve_empty_index():
    coll = MagicMock()
    client = MagicMock()
    retriever = CodeRetriever(
        collection=coll, chunks=[],
        embedding_model="text-embedding-3-small", openai_client=client,
    )
    results = retriever.retrieve("anything")
    assert results == []


def test_retrieve_passes_embedding_dimensions(sample_chunks, mock_collection, mock_openai_client):
    retriever = CodeRetriever(
        collection=mock_collection,
        chunks=sample_chunks,
        embedding_model="text-embedding-v4",
        openai_client=mock_openai_client,
        embedding_dimensions=1024,
    )

    retriever.retrieve("authenticate user login")

    mock_openai_client.embeddings.create.assert_called_once_with(
        input=["authenticate user login"],
        model="text-embedding-v4",
        dimensions=1024,
    )
