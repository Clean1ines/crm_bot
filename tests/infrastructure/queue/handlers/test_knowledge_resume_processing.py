from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.application.errors import EmbeddingProviderError, ValidationError
from src.infrastructure.queue.handlers.knowledge_resume_processing import (
    handle_resume_knowledge_processing,
)
from src.infrastructure.queue.job_exceptions import PermanentJobError, TransientJobError


@pytest.mark.asyncio
async def test_resume_handler_calls_ingestion_resume_processing_with_preprocessor_factory():
    job = {
        "payload": {
            "project_id": "project-1",
            "document_id": "doc-1",
        }
    }

    with patch(
        "src.infrastructure.queue.handlers.knowledge_resume_processing.KnowledgeIngestionService"
    ) as service_cls:
        service = Mock()
        service.resume_processing = AsyncMock()
        service_cls.return_value = service

        await handle_resume_knowledge_processing(job, db_pool=object())

    kwargs = service.resume_processing.await_args.kwargs
    assert kwargs["project_id"] == "project-1"
    assert kwargs["document_id"] == "doc-1"
    assert kwargs["preprocessor_factory"] is not None


@pytest.mark.asyncio
async def test_resume_handler_maps_validation_error_to_permanent_job_error():
    job = {"payload": {"project_id": "project-1", "document_id": "doc-1"}}

    with patch(
        "src.infrastructure.queue.handlers.knowledge_resume_processing.KnowledgeIngestionService"
    ) as service_cls:
        service = Mock()
        service.resume_processing = AsyncMock(side_effect=ValidationError("bad"))
        service_cls.return_value = service

        with pytest.raises(PermanentJobError):
            await handle_resume_knowledge_processing(job, db_pool=object())


@pytest.mark.asyncio
async def test_resume_handler_maps_retryable_embedding_error_to_transient_job_error():
    job = {"payload": {"project_id": "project-1", "document_id": "doc-1"}}

    with patch(
        "src.infrastructure.queue.handlers.knowledge_resume_processing.KnowledgeIngestionService"
    ) as service_cls:
        service = Mock()
        service.resume_processing = AsyncMock(
            side_effect=EmbeddingProviderError(
                "temporary",
                retryable=True,
                retry_after_seconds=12,
            )
        )
        service_cls.return_value = service

        with pytest.raises(TransientJobError):
            await handle_resume_knowledge_processing(job, db_pool=object())
