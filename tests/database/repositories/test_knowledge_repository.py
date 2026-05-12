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
from src.domain.project_plane.embedding_text import (
    CANONICAL_EMBEDDING_TEXT_VERSION,
    build_canonical_entry_embedding_text,
    build_retrieval_surface_search_text,
)
from src.domain.project_plane.knowledge_compilation import (
    CanonicalKnowledgeEntry,
    EmbeddingText,
    KnowledgeEnrichment,
    KnowledgeEntryKind,
    KnowledgeEntryStatus,
    KnowledgeEntryVisibility,
    SourceChunk,
    SourceRef,
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
    assert "DELETE FROM knowledge_documents WHERE project_id = $1" in executed_sql
    assert "DELETE FROM knowledge_base WHERE project_id = $1" not in executed_sql
    assert executed_sql.index("UPDATE execution_queue") < executed_sql.index(
        "DELETE FROM knowledge_documents WHERE project_id = $1"
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
    assert "DELETE FROM knowledge_base WHERE document_id = $1" not in executed_sql
    assert executed_sql.index("UPDATE execution_queue") < executed_sql.index(
        "DELETE FROM knowledge_documents WHERE id = $1"
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
    assert "DELETE FROM knowledge_base WHERE project_id = $1" not in executed_sql
    assert executed_sql.index("UPDATE execution_queue") < executed_sql.index(
        "DELETE FROM knowledge_documents WHERE project_id = $1"
    )


@patch("src.infrastructure.db.repositories.knowledge_repository.embed_batch")
async def test_add_canonical_entries_persists_entries_refs_and_retrieval_surface(
    mock_embed_batch,
    knowledge_repo,
    mock_pool,
):
    project_id = str(uuid4())
    document_id = str(uuid4())
    entry_id = str(uuid4())

    mock_embed_batch.return_value = EmbeddingBatchResult(embeddings=[[0.1, 0.2]])

    transaction = AsyncMock()
    transaction.__aenter__.return_value = mock_pool.mock_conn
    transaction.__aexit__.return_value = None
    mock_pool.mock_conn.transaction = MagicMock(return_value=transaction)
    mock_pool.mock_conn.execute = AsyncMock()

    entry = CanonicalKnowledgeEntry(
        id=entry_id,
        project_id=project_id,
        document_id=document_id,
        compiler_run_id="compiler-run-1",
        stable_key="stable-key-1",
        entry_kind=KnowledgeEntryKind.ANSWER,
        title="FAQ",
        answer="Typed answer content with enough useful words.",
        source_refs=(
            SourceRef(
                source_index=0,
                quote="Typed answer content",
                source_chunk_id=f"{document_id}:0",
                confidence=1.0,
            ),
        ),
        enrichment=KnowledgeEnrichment(
            questions=("Can I upload documents?",),
            synonyms=("upload docs",),
            tags=("docs",),
        ),
        embedding_text=EmbeddingText(
            value="FAQ upload documents typed embedding text",
            version="ignored_legacy_input",
        ),
        status=KnowledgeEntryStatus.PUBLISHED,
        visibility=KnowledgeEntryVisibility.RUNTIME,
        version=1,
        compiler_version="kcd_v1_stage_cd",
        embedding_text_version="ignored_legacy_input",
        metadata={"source": "test"},
    )

    result = await knowledge_repo.add_canonical_entries(
        project_id=project_id,
        document_id=document_id,
        entries=(entry,),
    )

    assert result == 1
    expected_embedding_text = build_canonical_entry_embedding_text(entry).value
    mock_embed_batch.assert_awaited_once_with([expected_embedding_text])

    executed_sql = "\n".join(
        str(call_item.args[0])
        for call_item in mock_pool.mock_conn.execute.await_args_list
    )
    assert "INSERT INTO knowledge_entries" in executed_sql
    assert "INSERT INTO knowledge_entry_source_refs" in executed_sql
    assert "INSERT INTO knowledge_retrieval_surface" in executed_sql
    assert "INSERT INTO knowledge_base" not in executed_sql

    first_insert_args = mock_pool.mock_conn.execute.await_args_list[0].args
    assert "INSERT INTO knowledge_entries" in first_insert_args[0]
    assert first_insert_args[5] == "stable-key-1"
    assert first_insert_args[6] == "answer"
    assert first_insert_args[7] == "FAQ"
    assert first_insert_args[8] == "Typed answer content with enough useful words."
    assert first_insert_args[9] == "published"
    assert first_insert_args[10] == "runtime"
    assert first_insert_args[12] == "kcd_v1_stage_cd"
    assert first_insert_args[13] == expected_embedding_text
    assert first_insert_args[14] == CANONICAL_EMBEDDING_TEXT_VERSION

    source_ref_insert_args = mock_pool.mock_conn.execute.await_args_list[2].args
    assert "INSERT INTO knowledge_entry_source_refs" in source_ref_insert_args[0]
    assert source_ref_insert_args[2] == f"{document_id}:0"
    assert source_ref_insert_args[3] == 0
    assert source_ref_insert_args[4] == "Typed answer content"

    surface_insert_args = mock_pool.mock_conn.execute.await_args_list[4].args
    assert "INSERT INTO knowledge_retrieval_surface" in surface_insert_args[0]
    assert surface_insert_args[4] == "stable-key-1"
    assert surface_insert_args[5] == "answer"
    assert surface_insert_args[6] == "FAQ"
    assert surface_insert_args[7] == "Typed answer content with enough useful words."
    assert surface_insert_args[8] == expected_embedding_text
    assert surface_insert_args[9] == CANONICAL_EMBEDDING_TEXT_VERSION
    assert surface_insert_args[11] == build_retrieval_surface_search_text(entry)


def test_search_filters_non_answer_knowledge_roles() -> None:
    source = Path(
        "src/infrastructure/db/repositories/knowledge_repository.py"
    ).read_text(encoding="utf-8")

    assert "ANSWERABLE_KNOWLEDGE_ENTRY_KINDS" in source
    assert "AND rs.entry_kind = ANY($4::text[])" in source
    assert "AND rs.entry_kind = ANY($6::text[])" in source
    assert "rs.status = 'published'" in source
    assert "rs.visibility = 'runtime'" in source
    assert "knowledge_retrieval_surface AS rs" in source
    assert "kb.entry_kind = ANY" not in source
    assert "entry_type" not in source
    assert '"debug_artifact"' not in source


def test_answerable_search_filter_uses_retrieval_surface_contract() -> None:
    source = Path(
        "src/infrastructure/db/repositories/knowledge_repository.py"
    ).read_text(encoding="utf-8")

    assert "RUNTIME_ENTRY_KIND_VALUES" in source
    assert "ANSWERABLE_KNOWLEDGE_ENTRY_KINDS" in source
    assert "tuple(sorted(RUNTIME_ENTRY_KIND_VALUES))" in source


def test_search_returns_metadata_observability_fields() -> None:
    source = Path(
        "src/infrastructure/db/repositories/knowledge_repository.py"
    ).read_text(encoding="utf-8")
    search_source = source[
        source.index("    async def search(") : source.index(
            "    async def preview_search("
        )
    ]

    assert "knowledge_retrieval_surface AS rs" in search_source
    assert "rs.entry_kind," in search_source
    assert "rs.title," in search_source
    assert "rs.source_refs," in search_source
    assert "rs.embedding_text," in search_source
    assert "rs.enrichment->'questions' AS questions" in search_source
    assert "rs.enrichment->'synonyms' AS synonyms" in search_source
    assert "rs.enrichment->'tags' AS tags" in search_source
    assert "source_refs=_source_ref_views_from_payload" not in search_source
    assert "source_refs=source_refs" in search_source
    assert "source_refs_from_excerpt" not in search_source
    assert "knowledge_base" not in search_source


@pytest.mark.asyncio
async def test_add_source_chunks_persists_raw_source_chunks(
    knowledge_repo,
    mock_pool,
):
    project_id = "00000000-0000-0000-0000-000000000001"
    document_id = "00000000-0000-0000-0000-000000000002"
    chunk = SourceChunk(
        id=f"{document_id}:0",
        project_id=project_id,
        document_id=document_id,
        source_index=0,
        content="Raw source evidence text.",
        page=2,
        section_title="Evidence",
        checksum="checksum-1",
        metadata={"upload_chunk_index": 0},
    )

    class _FakeTransaction:
        async def __aenter__(self) -> None:
            return None

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    mock_pool.mock_conn.transaction = Mock(return_value=_FakeTransaction())

    result = await knowledge_repo.add_source_chunks(
        project_id=project_id,
        document_id=document_id,
        chunks=(chunk,),
    )

    assert result == 1
    calls = mock_pool.mock_conn.execute.await_args_list
    assert "DELETE FROM knowledge_source_chunks" in calls[-2].args[0]

    insert_args = calls[-1].args
    assert "INSERT INTO knowledge_source_chunks" in insert_args[0]
    assert insert_args[1] == f"{document_id}:0"
    assert insert_args[4] == 0
    assert insert_args[5] == "Raw source evidence text."
    assert insert_args[6] == 2
    assert insert_args[7] == "Evidence"
    assert insert_args[10] == "checksum-1"
    assert '"upload_chunk_index": 0' in insert_args[11]
