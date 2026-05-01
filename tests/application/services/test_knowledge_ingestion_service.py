import pytest
from unittest.mock import AsyncMock, Mock

from src.application.errors import (
    PermanentEmbeddingProviderError,
    TransientEmbeddingProviderError,
)
from src.application.services.knowledge_ingestion_service import (
    KnowledgeIngestionService,
)


@pytest.mark.asyncio
async def test_process_document_marks_plain_upload_processed():
    repo = Mock()
    repo.delete_document_chunks = AsyncMock()
    repo.add_knowledge_batch = AsyncMock(return_value=2)
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()
    repo.add_structured_knowledge_batch = AsyncMock(return_value=0)

    service = KnowledgeIngestionService(object())

    result = await service.process_document(
        project_id="project-1",
        document_id="doc-1",
        file_name="test.txt",
        chunks=[{"content": "one"}, {"content": "two"}],
        mode="plain",
        knowledge_repo_factory=Mock(return_value=repo),
        preprocessor_factory=None,
        logger=Mock(),
    )

    assert result.document_id == "doc-1"
    assert result.preprocessing_status == "not_requested"
    assert result.structured_entries == 0
    repo.delete_document_chunks.assert_awaited_once_with("doc-1")
    repo.add_knowledge_batch.assert_awaited_once_with(
        "project-1",
        [{"content": "one"}, {"content": "two"}],
        document_id="doc-1",
    )
    repo.update_document_preprocessing_status.assert_awaited_once_with(
        "doc-1",
        mode="plain",
        status="not_requested",
    )
    repo.update_document_status.assert_awaited_once_with("doc-1", "processed")


@pytest.mark.asyncio
async def test_process_document_marks_document_error_on_embedding_failure():
    repo = Mock()
    repo.delete_document_chunks = AsyncMock()
    repo.add_knowledge_batch = AsyncMock(side_effect=RuntimeError("embed failed"))
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()

    service = KnowledgeIngestionService(object())

    with pytest.raises(RuntimeError, match="embed failed"):
        await service.process_document(
            project_id="project-1",
            document_id="doc-err",
            file_name="test.txt",
            chunks=[{"content": "one"}],
            mode="plain",
            knowledge_repo_factory=Mock(return_value=repo),
            preprocessor_factory=None,
            logger=Mock(),
        )

    repo.update_document_status.assert_awaited_once_with(
        "doc-err", "error", "embed failed"
    )


@pytest.mark.asyncio
async def test_process_document_retries_transient_embedding_provider_failure():
    repo = Mock()
    repo.delete_document_chunks = AsyncMock()
    repo.add_knowledge_batch = AsyncMock(
        side_effect=TransientEmbeddingProviderError(
            "Embedding provider temporary failure",
            provider="voyage",
            task="document",
            model="voyage-4-lite",
        )
    )
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()

    service = KnowledgeIngestionService(object())

    with pytest.raises(TransientEmbeddingProviderError):
        await service.process_document(
            project_id="project-1",
            document_id="doc-retry",
            file_name="test.txt",
            chunks=[{"content": "one"}],
            mode="plain",
            knowledge_repo_factory=Mock(return_value=repo),
            preprocessor_factory=None,
            logger=Mock(),
        )

    repo.update_document_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_process_document_marks_document_error_on_permanent_provider_failure():
    repo = Mock()
    repo.delete_document_chunks = AsyncMock()
    repo.add_knowledge_batch = AsyncMock(
        side_effect=PermanentEmbeddingProviderError(
            "Embedding provider access denied",
            provider="voyage",
            task="document",
            model="voyage-4-lite",
        )
    )
    repo.update_document_status = AsyncMock()
    repo.update_document_preprocessing_status = AsyncMock()

    service = KnowledgeIngestionService(object())

    with pytest.raises(PermanentEmbeddingProviderError):
        await service.process_document(
            project_id="project-1",
            document_id="doc-perm",
            file_name="test.txt",
            chunks=[{"content": "one"}],
            mode="plain",
            knowledge_repo_factory=Mock(return_value=repo),
            preprocessor_factory=None,
            logger=Mock(),
        )

    repo.update_document_status.assert_awaited_once_with(
        "doc-perm", "error", "Embedding provider access denied"
    )
