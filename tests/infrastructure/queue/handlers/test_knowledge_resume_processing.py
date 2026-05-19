from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.infrastructure.queue.handlers.knowledge_resume_processing import (
    handle_resume_knowledge_processing,
)


@pytest.mark.asyncio
async def test_resume_handler_calls_ingestion_resume_processing():
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

    service.resume_processing.assert_awaited_once()
