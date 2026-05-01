from unittest.mock import AsyncMock, Mock

import pytest

from src.application.errors import (
    PermanentEmbeddingProviderError,
    TransientEmbeddingProviderError,
)
from src.infrastructure.queue.handlers import knowledge_upload
from src.infrastructure.queue.job_exceptions import PermanentJobError, TransientJobError


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
        )
    )
    monkeypatch.setattr(
        knowledge_upload,
        "KnowledgeIngestionService",
        Mock(return_value=service),
    )

    with pytest.raises(TransientJobError, match="Embedding provider temporary failure"):
        await knowledge_upload.handle_process_knowledge_upload(
            {
                "payload": {
                    "project_id": "project-1",
                    "document_id": "doc-1",
                    "file_name": "doc.txt",
                    "preprocessing_mode": "plain",
                    "chunks": [{"content": "hello"}],
                }
            },
            db_pool=object(),
        )


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
            {
                "payload": {
                    "project_id": "project-1",
                    "document_id": "doc-1",
                    "file_name": "doc.txt",
                    "preprocessing_mode": "plain",
                    "chunks": [{"content": "hello"}],
                }
            },
            db_pool=object(),
        )
