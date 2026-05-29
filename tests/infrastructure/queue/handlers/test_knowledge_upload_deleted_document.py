from __future__ import annotations

from collections.abc import Mapping

import pytest

from src.application.errors import KnowledgeDocumentDeletedDuringProcessingError
from src.infrastructure.queue.handlers import knowledge_upload
from src.infrastructure.queue.job_exceptions import PermanentJobError


class FakeIngestionService:
    def __init__(self, _pool: object) -> None:
        pass

    async def process_document(self, **_kwargs: object) -> None:
        raise KnowledgeDocumentDeletedDuringProcessingError(
            "Knowledge document was deleted or reset during processing"
        )


@pytest.mark.asyncio
async def test_deleted_document_during_upload_is_permanent_job_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recovery_calls: list[Mapping[str, object]] = []

    async def mark_recoverable(**kwargs: object) -> None:
        recovery_calls.append(dict(kwargs))

    monkeypatch.setattr(
        knowledge_upload,
        "KnowledgeStructuredIngestionService",
        FakeIngestionService,
    )
    monkeypatch.setattr(
        knowledge_upload,
        "_mark_recoverable_llm_upload_failure",
        mark_recoverable,
    )

    job = {
        "payload": {
            "project_id": "project-1",
            "document_id": "document-1",
            "file_name": "knowledge.md",
            "chunks": [{"content": "hello"}],
            "preprocessing_mode": "plain",
        }
    }

    with pytest.raises(PermanentJobError):
        await knowledge_upload.handle_process_knowledge_upload(job, db_pool=object())

    assert recovery_calls == []
