from unittest.mock import AsyncMock, MagicMock, Mock, call, patch
from uuid import UUID, uuid4

import pytest

from src.domain.project_plane.model_usage_views import ModelUsageMeasurement
from src.infrastructure.db.repositories.knowledge_repository import KnowledgeRepository
from src.infrastructure.llm.embedding_service import (
    EmbeddingBatchResult,
    EmbeddingTextResult,
)


@pytest.fixture
def mock_pool():
    pool = AsyncMock()
    mock_conn = AsyncMock()
    mock_cm = AsyncMock()
    mock_cm.__aenter__.return_value = mock_conn
    mock_cm.__aexit__.return_value = None
    pool.acquire = MagicMock(return_value=mock_cm)
    pool.mock_conn = mock_conn
    return pool


@pytest.fixture
def knowledge_repo(mock_pool):
    return KnowledgeRepository(mock_pool)


@pytest.mark.asyncio
@patch("src.infrastructure.db.repositories.knowledge_repository.embed_text")
async def test_search_success_hybrid_true(
    mock_embed_text,
    knowledge_repo,
    mock_pool,
):
    project_id = str(uuid4())
    query = "test query"
    mock_embed_text.return_value = EmbeddingTextResult(embedding=[0.1, 0.2, 0.3])
    vector_rows = [
        {"id": uuid4(), "content": "vector chunk 1", "score": 0.9},
        {"id": uuid4(), "content": "vector chunk 2", "score": 0.8},
    ]
    fts_rows = [
        {"id": vector_rows[0]["id"], "content": "vector chunk 1", "score": 0.85},
        {"id": uuid4(), "content": "fts only chunk", "score": 0.7},
    ]
    mock_pool.mock_conn.fetch = AsyncMock(side_effect=[vector_rows, fts_rows])

    result = await knowledge_repo.search(
        project_id,
        query,
        limit=10,
        hybrid_fallback=True,
    )

    mock_embed_text.assert_awaited_once_with(query)
    assert len(result) == 3
    assert mock_pool.acquire.call_count == 1
    assert all(item.id and item.content and item.method for item in result)


@pytest.mark.asyncio
@patch("src.infrastructure.db.repositories.knowledge_repository.embed_text")
async def test_search_records_rag_embedding_usage(
    mock_embed_text,
    knowledge_repo,
    mock_pool,
    monkeypatch: pytest.MonkeyPatch,
):
    usage = ModelUsageMeasurement(
        provider="voyage",
        model="voyage-4-lite",
        usage_type="embedding",
        tokens_input=10,
        tokens_output=None,
        tokens_total=10,
        estimated_cost_usd=None,
        metadata={"is_estimated": False},
    )
    usage_repo = Mock()
    usage_repo.record_event = AsyncMock()
    monkeypatch.setattr(knowledge_repo, "_usage_repo", usage_repo)
    mock_embed_text.return_value = EmbeddingTextResult(
        embedding=[0.1, 0.2, 0.3],
        usage=usage,
    )
    mock_pool.mock_conn.fetch = AsyncMock(side_effect=[[], []])

    await knowledge_repo.search(
        str(uuid4()),
        "rag query",
        thread_id="thread-1",
    )

    usage_repo.record_event.assert_awaited_once()
    recorded_event = usage_repo.record_event.await_args.args[0]
    assert recorded_event.source == "rag_search"
    assert recorded_event.thread_id == "thread-1"
    assert recorded_event.provider == "voyage"


@pytest.mark.asyncio
@patch("src.infrastructure.db.repositories.knowledge_repository.embed_text")
async def test_preview_search_does_not_request_embeddings(
    mock_embed_text,
    knowledge_repo,
    mock_pool,
):
    mock_pool.mock_conn.fetch = AsyncMock(return_value=[])

    result = await knowledge_repo.preview_search(str(uuid4()), "q", limit=5)

    assert result == []
    mock_embed_text.assert_not_awaited()


@pytest.mark.asyncio
@patch("src.infrastructure.db.repositories.knowledge_repository.embed_batch")
async def test_add_knowledge_batch_success(
    mock_embed_batch,
    knowledge_repo,
    mock_pool,
    monkeypatch: pytest.MonkeyPatch,
):
    project_id = str(uuid4())
    document_id = str(uuid4())
    usage_repo = Mock()
    usage_repo.record_event = AsyncMock()
    monkeypatch.setattr(knowledge_repo, "_usage_repo", usage_repo)
    mock_embed_batch.return_value = EmbeddingBatchResult(
        embeddings=[[0.1, 0.2], [0.3, 0.4]],
    )
    transaction = AsyncMock()
    transaction.__aenter__.return_value = mock_pool.mock_conn
    transaction.__aexit__.return_value = None
    mock_pool.mock_conn.transaction = MagicMock(return_value=transaction)
    mock_pool.mock_conn.execute = AsyncMock()

    result = await knowledge_repo.add_knowledge_batch(
        project_id,
        [{"content": "chunk1"}, {"content": "chunk2"}],
        document_id,
    )

    assert result == 2
    assert mock_embed_batch.await_args_list == [
        call(["chunk1"]),
        call(["chunk2"]),
    ]
    assert mock_pool.mock_conn.transaction.call_count == 2
    assert mock_pool.mock_conn.execute.await_count == 2
    usage_repo.record_event.assert_not_awaited()


@pytest.mark.asyncio
@patch("src.infrastructure.db.repositories.knowledge_repository.embed_batch")
async def test_add_knowledge_batch_gets_embeddings_before_opening_transaction(
    mock_embed_batch,
    knowledge_repo,
    mock_pool,
):
    order: list[str] = []

    async def fake_embed_batch(texts: list[str]) -> EmbeddingBatchResult:
        order.append("embed_batch")
        return EmbeddingBatchResult(embeddings=[[0.1, 0.2]])

    def fake_transaction():
        order.append("transaction")
        transaction = AsyncMock()
        transaction.__aenter__.return_value = mock_pool.mock_conn
        transaction.__aexit__.return_value = None
        return transaction

    mock_embed_batch.side_effect = fake_embed_batch
    mock_pool.mock_conn.transaction = fake_transaction
    mock_pool.mock_conn.execute = AsyncMock()

    await knowledge_repo.add_knowledge_batch(str(uuid4()), [{"content": "chunk"}])

    assert order == ["embed_batch", "transaction"]


@pytest.mark.asyncio
@patch("src.infrastructure.db.repositories.knowledge_repository.embed_batch")
async def test_add_knowledge_batch_records_usage_for_document_embeddings(
    mock_embed_batch,
    knowledge_repo,
    mock_pool,
    monkeypatch: pytest.MonkeyPatch,
):
    document_id = str(uuid4())
    usage = ModelUsageMeasurement(
        provider="voyage",
        model="voyage-4-lite",
        usage_type="embedding",
        tokens_input=12,
        tokens_output=None,
        tokens_total=12,
        estimated_cost_usd=None,
        metadata={"is_estimated": False},
    )
    usage_repo = Mock()
    usage_repo.record_event = AsyncMock()
    monkeypatch.setattr(knowledge_repo, "_usage_repo", usage_repo)
    mock_embed_batch.return_value = EmbeddingBatchResult(
        embeddings=[[0.1, 0.2]],
        usage=usage,
    )
    transaction = AsyncMock()
    transaction.__aenter__.return_value = mock_pool.mock_conn
    transaction.__aexit__.return_value = None
    mock_pool.mock_conn.transaction = MagicMock(return_value=transaction)
    mock_pool.mock_conn.execute = AsyncMock()

    await knowledge_repo.add_knowledge_batch(
        str(uuid4()),
        [{"content": "chunk"}],
        document_id=document_id,
    )

    usage_repo.record_event.assert_awaited_once()
    recorded_event = usage_repo.record_event.await_args.args[0]
    assert recorded_event.source == "knowledge_upload"
    assert recorded_event.document_id == document_id
    assert recorded_event.tokens_total == 12


@pytest.mark.asyncio
@patch("src.infrastructure.db.repositories.knowledge_repository.embed_batch")
async def test_add_structured_knowledge_batch_success(
    mock_embed_batch,
    knowledge_repo,
    mock_pool,
):
    mock_embed_batch.return_value = EmbeddingBatchResult(embeddings=[[0.1, 0.2]])
    transaction = AsyncMock()
    transaction.__aenter__.return_value = mock_pool.mock_conn
    transaction.__aexit__.return_value = None
    mock_pool.mock_conn.transaction = MagicMock(return_value=transaction)
    mock_pool.mock_conn.execute = AsyncMock()

    result = await knowledge_repo.add_structured_knowledge_batch(
        str(uuid4()),
        [
            {
                "content": "answer",
                "entry_type": "faq",
                "title": "Title",
                "source_excerpt": "source",
                "questions": ["question"],
                "synonyms": ["synonym"],
                "tags": ["tag"],
                "embedding_text": "Title answer question",
            }
        ],
        str(uuid4()),
    )

    assert result == 1
    mock_embed_batch.assert_awaited_once_with(["Title answer question"])
    executed_sql = mock_pool.mock_conn.execute.await_args.args[0]
    assert "embedding_text" in executed_sql


@pytest.mark.asyncio
async def test_clear_project_knowledge_success(knowledge_repo, mock_pool):
    project_id = str(uuid4())
    mock_pool.mock_conn.execute = AsyncMock()
    transaction = AsyncMock()
    transaction.__aenter__.return_value = mock_pool.mock_conn
    transaction.__aexit__.return_value = None
    mock_pool.mock_conn.transaction = MagicMock(return_value=transaction)

    await knowledge_repo.clear_project_knowledge(project_id)

    calls = [
        call("DELETE FROM knowledge_base WHERE project_id = $1", UUID(project_id)),
        call("DELETE FROM knowledge_documents WHERE project_id = $1", UUID(project_id)),
    ]
    mock_pool.mock_conn.execute.assert_has_calls(calls, any_order=False)
