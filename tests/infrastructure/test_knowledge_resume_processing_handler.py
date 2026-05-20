import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from src.application.errors import ValidationError
from src.infrastructure.queue.handlers.knowledge_resume_processing import handle_resume_knowledge_processing
from src.infrastructure.queue.job_exceptions import PermanentJobError


def test_resume_handler_calls_true_resume_processing() -> None:
    job = {"payload": {"project_id": "p1", "document_id": "d1"}}
    service = Mock()
    service.resume_processing = AsyncMock(return_value={"status": "completed"})
    with patch("src.infrastructure.queue.handlers.knowledge_resume_processing.KnowledgeIngestionService", return_value=service):
        asyncio.run(handle_resume_knowledge_processing(job, db_pool=Mock()))
    service.resume_processing.assert_awaited_once()


def test_resume_handler_maps_validation_to_permanent_error() -> None:
    job = {"payload": {"project_id": "p1", "document_id": "d1"}}
    service = Mock()
    service.resume_processing = AsyncMock(side_effect=ValidationError("bad"))
    with patch("src.infrastructure.queue.handlers.knowledge_resume_processing.KnowledgeIngestionService", return_value=service):
        with pytest.raises(PermanentJobError):
            asyncio.run(handle_resume_knowledge_processing(job, db_pool=Mock()))
