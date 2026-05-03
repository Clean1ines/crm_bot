from unittest.mock import AsyncMock, Mock

import pytest

from src.application.errors import (
    PermanentEmbeddingProviderError,
    TransientEmbeddingProviderError,
)
from src.infrastructure.queue.handlers import knowledge_upload
from src.infrastructure.queue.job_exceptions import PermanentJobError, TransientJobError


def _payload() -> dict[str, object]:
    return {
        "payload": {
            "project_id": "project-1",
            "document_id": "doc-1",
            "file_name": "doc.txt",
            "preprocessing_mode": "plain",
            "chunks": [{"content": "hello"}],
        }
    }


@pytest.mark.asyncio
async def test_handle_process_knowledge_upload_maps_transient_embedding_error(
    monkeypatch: pytest.MonkeyPatch,
):
    service = Mock()
    service.process_document = AsyncMock(
        side_effect=TransientEmbeddingProviderError(
            "Embedding provider temporary failure",
            provider="voyage",
            task="document",
            model="voyage-4-lite",
            retry_after_seconds=91.0,
        )
    )
    monkeypatch.setattr(
        knowledge_upload,
        "KnowledgeIngestionService",
        Mock(return_value=service),
    )

    with pytest.raises(TransientJobError) as exc_info:
        await knowledge_upload.handle_process_knowledge_upload(
            _payload(),
            db_pool=object(),
        )

    assert str(exc_info.value) == "Embedding provider temporary failure"
    assert exc_info.value.retry_after_seconds == 91.0


@pytest.mark.asyncio
async def test_handle_process_knowledge_upload_maps_permanent_embedding_error(
    monkeypatch: pytest.MonkeyPatch,
):
    service = Mock()
    service.process_document = AsyncMock(
        side_effect=PermanentEmbeddingProviderError(
            "Embedding provider access denied",
            provider="voyage",
            task="document",
            model="voyage-4-lite",
        )
    )
    monkeypatch.setattr(
        knowledge_upload,
        "KnowledgeIngestionService",
        Mock(return_value=service),
    )

    with pytest.raises(PermanentJobError, match="Embedding provider access denied"):
        await knowledge_upload.handle_process_knowledge_upload(
            _payload(),
            db_pool=object(),
        )


@pytest.mark.asyncio
async def test_mark_process_knowledge_upload_exhausted_marks_document_error(
    monkeypatch: pytest.MonkeyPatch,
):
    repo = Mock()
    repo.update_document_status = AsyncMock()
    monkeypatch.setattr(
        knowledge_upload,
        "KnowledgeRepository",
        Mock(return_value=repo),
    )

    await knowledge_upload.mark_process_knowledge_upload_exhausted(
        _payload(),
        db_pool=object(),
    )

    repo.update_document_status.assert_awaited_once_with(
        "doc-1",
        "error",
        knowledge_upload.EXHAUSTED_KNOWLEDGE_UPLOAD_DETAIL,
    )
