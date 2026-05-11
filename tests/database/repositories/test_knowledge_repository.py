from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch
from uuid import uuid4

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
    rows = [
        {
            "id": uuid4(),
            "content": "vector chunk 1",
            "document_id": None,
            "source": None,
            "document_status": None,
            "search_text": "vector chunk 1 test query",
            "vector_score": 0.9,
            "lexical_score": 0.85,
            "exact_score": 0.0,
            "method": "hybrid",
        },
        {
            "id": uuid4(),
            "content": "vector chunk 2",
            "document_id": None,
            "source": None,
            "document_status": None,
            "search_text": "vector chunk 2",
            "vector_score": 0.8,
            "lexical_score": 0.0,
            "exact_score": 0.0,
            "method": "vector",
        },
        {
            "id": uuid4(),
            "content": "fts only chunk",
            "document_id": None,
            "source": None,
            "document_status": None,
            "search_text": "fts only chunk test query",
            "vector_score": 0.0,
            "lexical_score": 0.7,
            "exact_score": 0.0,
            "method": "fts",
        },
    ]
    mock_pool.mock_conn.fetch = AsyncMock(return_value=rows)

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
async def test_clear_project_knowledge_success(knowledge_repo, mock_pool):
    project_id = str(uuid4())
    transaction = AsyncMock()
    transaction.__aenter__.return_value = mock_pool.mock_conn
    transaction.__aexit__.return_value = None
    mock_pool.mock_conn.transaction = MagicMock(return_value=transaction)

    await knowledge_repo.clear_project_knowledge(project_id)

    executed_sql = "\n".join(
        str(call_item.args[0])
        for call_item in mock_pool.mock_conn.execute.await_args_list
    )

    assert "UPDATE execution_queue" in executed_sql
    assert "payload::jsonb ->> 'project_id' = $3" in executed_sql
    assert "DELETE FROM knowledge_base WHERE project_id = $1" in executed_sql
    assert "DELETE FROM knowledge_documents WHERE project_id = $1" in executed_sql
    assert executed_sql.index("UPDATE execution_queue") < executed_sql.index(
        "DELETE FROM knowledge_base WHERE project_id = $1"
    )


class _RecordingTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> bool:
        return False


class RecordingConnection:
    def __init__(self) -> None:
        self.execute_calls: list[tuple[str, tuple[object, ...]]] = []

    async def execute(self, query: str, *args: object) -> str:
        self.execute_calls.append((query, args))
        return "UPDATE 1"

    def transaction(self) -> _RecordingTransaction:
        return _RecordingTransaction()


class _RecordingAcquire:
    def __init__(self, conn: RecordingConnection) -> None:
        self._conn = conn

    async def __aenter__(self) -> RecordingConnection:
        return self._conn

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> bool:
        return False


class RecordingPool:
    def __init__(self, conn: RecordingConnection) -> None:
        self._conn = conn

    def acquire(self) -> _RecordingAcquire:
        return _RecordingAcquire(self._conn)


async def test_delete_document_cancels_related_queue_jobs_before_hard_delete() -> None:
    document_id = str(uuid4())
    conn = RecordingConnection()
    repo = KnowledgeRepository(RecordingPool(conn))

    await repo.delete_document(document_id)

    executed_sql = "\n".join(execute_call[0] for execute_call in conn.execute_calls)

    assert "UPDATE execution_queue" in executed_sql
    assert "payload::jsonb ->> 'document_id' = $3" in executed_sql
    assert "process_knowledge_upload" in repr(conn.execute_calls)
    assert "run_full_rag_eval" in repr(conn.execute_calls)
    assert executed_sql.index("UPDATE execution_queue") < executed_sql.index(
        "DELETE FROM knowledge_base WHERE document_id = $1"
    )


async def test_clear_project_knowledge_cancels_project_jobs_before_hard_delete() -> (
    None
):
    project_id = str(uuid4())
    conn = RecordingConnection()
    repo = KnowledgeRepository(RecordingPool(conn))

    await repo.clear_project_knowledge(project_id)

    executed_sql = "\n".join(execute_call[0] for execute_call in conn.execute_calls)

    assert "UPDATE execution_queue" in executed_sql
    assert "payload::jsonb ->> 'project_id' = $3" in executed_sql
    assert "process_knowledge_upload" in repr(conn.execute_calls)
    assert "run_full_rag_eval" in repr(conn.execute_calls)
    assert executed_sql.index("UPDATE execution_queue") < executed_sql.index(
        "DELETE FROM knowledge_base WHERE project_id = $1"
    )


@patch("src.infrastructure.db.repositories.knowledge_repository.embed_batch")
async def test_add_knowledge_chunks_persists_typed_chunks(
    mock_embed_batch,
    knowledge_repo,
    mock_pool,
):
    from src.domain.project_plane.knowledge_chunks import (
        KnowledgeChunk,
        KnowledgeChunkDraft,
        KnowledgeChunkRole,
        KnowledgeSectionPath,
    )

    project_id = str(uuid4())
    document_id = str(uuid4())
    mock_embed_batch.return_value = EmbeddingBatchResult(embeddings=[[0.1, 0.2]])
    transaction = AsyncMock()
    transaction.__aenter__.return_value = mock_pool.mock_conn
    transaction.__aexit__.return_value = None
    mock_pool.mock_conn.transaction = MagicMock(return_value=transaction)
    mock_pool.mock_conn.execute = AsyncMock()

    chunk = KnowledgeChunk.from_draft(
        project_id=project_id,
        document_id=document_id,
        draft=KnowledgeChunkDraft(
            content="Typed answer content with enough useful words.",
            role=KnowledgeChunkRole.FAQ,
            title="FAQ",
            source_excerpt="Typed answer content",
            section_path=KnowledgeSectionPath(
                document_title="knowledge.md",
                headings=("FAQ",),
            ),
            questions=("Can I upload documents?",),
            synonyms=("upload docs",),
            tags=("docs",),
            embedding_text="FAQ upload documents typed embedding text",
        ),
    )

    result = await knowledge_repo.add_knowledge_chunks(
        project_id=project_id,
        document_id=document_id,
        chunks=(chunk,),
    )

    assert result == 1
    mock_embed_batch.assert_awaited_once_with(
        ["FAQ upload documents typed embedding text"]
    )
    executed_args = mock_pool.mock_conn.execute.await_args.args
    assert "embedding_text" in executed_args[0]
    assert executed_args[3] == "Typed answer content with enough useful words."
    assert executed_args[5] == "faq"
    assert executed_args[6] == "FAQ"
    assert executed_args[7] == "Typed answer content"
    assert executed_args[8] == '["Can I upload documents?"]'
    assert executed_args[9] == '["upload docs"]'
    assert executed_args[10] == '["docs"]'
    assert executed_args[11] == "FAQ upload documents typed embedding text"


def test_search_filters_non_answer_knowledge_roles() -> None:
    source = Path(
        "src/infrastructure/db/repositories/knowledge_repository.py"
    ).read_text(encoding="utf-8")

    assert "ANSWERABLE_KNOWLEDGE_ENTRY_TYPES" in source
    assert "AND kb.entry_type = ANY($4::text[])" in source
    assert "AND kb.entry_type = ANY($6::text[])" in source
    assert '"internal_eval_test"' not in source
    assert '"negative_test"' not in source
    assert '"retrieval_guideline"' not in source


def test_answerable_search_filter_uses_domain_role_contract() -> None:
    source = Path(
        "src/infrastructure/db/repositories/knowledge_repository.py"
    ).read_text(encoding="utf-8")

    assert "ANSWERABLE_KNOWLEDGE_ROLES" in source
    assert "sorted(role.value for role in ANSWERABLE_KNOWLEDGE_ROLES)" in source


def test_search_returns_metadata_observability_fields() -> None:
    source = Path(
        "src/infrastructure/db/repositories/knowledge_repository.py"
    ).read_text(encoding="utf-8")
    search_source = source[
        source.index("    async def search(") : source.index(
            "    async def preview_search("
        )
    ]

    assert "kb.entry_type," in search_source
    assert "kb.title," in search_source
    assert "kb.source_excerpt," in search_source
    assert "kb.embedding_text," in search_source
    assert "kb.questions," in search_source
    assert "kb.synonyms," in search_source
    assert "kb.tags," in search_source
    assert "max(entry_type) AS entry_type" in search_source
    assert "(jsonb_agg(questions)->0) AS questions" in search_source
    assert "(jsonb_agg(synonyms)->0) AS synonyms" in search_source
    assert "(jsonb_agg(tags)->0) AS tags" in search_source
    assert "max(questions) AS questions" not in search_source
    assert "max(synonyms) AS synonyms" not in search_source
    assert "max(tags) AS tags" not in search_source
    assert 'entry_type=_optional_row_text(row, "entry_type"),' in search_source
    assert 'title=_optional_row_text(row, "title"),' in search_source
    assert 'source_excerpt=_optional_row_text(row, "source_excerpt"),' in search_source
    assert 'embedding_text=_optional_row_text(row, "embedding_text"),' in search_source
    assert 'questions=_optional_row_value(row, "questions"),' in search_source
    assert 'synonyms=_optional_row_value(row, "synonyms"),' in search_source
    assert 'tags=_optional_row_value(row, "tags"),' in search_source
