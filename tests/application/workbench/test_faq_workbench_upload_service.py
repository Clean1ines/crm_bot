from __future__ import annotations

import pytest

from src.application.services.faq_workbench_fresh_upload_service import (
    MonotonicIdFactory,
)
from src.application.workbench.upload_service import (
    FaqWorkbenchUploadCommand,
    FaqWorkbenchUploadService,
)
from tests.application.workbench.helpers import (
    InMemoryWorkbenchQueue,
    InMemoryWorkbenchRepository,
)


@pytest.mark.asyncio
async def test_workbench_upload_creates_lineage_and_enqueues_process_document() -> None:
    repository = InMemoryWorkbenchRepository()
    queue = InMemoryWorkbenchQueue()
    service = FaqWorkbenchUploadService(
        repository,
        queue,
        id_factory=MonotonicIdFactory.create(),
    )

    result = await service.upload_markdown(
        FaqWorkbenchUploadCommand(
            project_id="project-1",
            file_name="knowledge.md",
            upload_id="upload-1",
            raw_text="# Product\nProduct text.\n\n## Curation\nCuration text.",
            file_size_bytes=len(
                b"# Product\nProduct text.\n\n## Curation\nCuration text."
            ),
            content_hash="hash-1",
        )
    )

    assert repository.documents == [result.upload.document]
    assert result.upload.document.file_size_bytes == len(
        b"# Product\nProduct text.\n\n## Curation\nCuration text."
    )

    assert len(queue.payloads) == 1
    payload = queue.payloads[0]
    queue_payload = payload.to_queue_payload()

    assert payload.project_id == result.upload.document.project_id
    assert payload.document_id == result.upload.document.document_id
    assert payload.processing_run_id == result.upload.processing_run.processing_run_id

    assert queue_payload == {
        "project_id": result.upload.document.project_id,
        "document_id": result.upload.document.document_id,
        "processing_run_id": result.upload.processing_run.processing_run_id,
        "processing_method": "faq_section_registry_v1",
        "trigger": "fresh_upload",
        "source": "workbench_fresh_upload",
    }


@pytest.mark.asyncio
async def test_workbench_upload_queue_payload_uses_processing_run_id() -> None:
    repository = InMemoryWorkbenchRepository()
    queue = InMemoryWorkbenchQueue()
    service = FaqWorkbenchUploadService(
        repository,
        queue,
        id_factory=MonotonicIdFactory.create(),
    )

    result = await service.upload_markdown(
        FaqWorkbenchUploadCommand(
            project_id="project-1",
            file_name="knowledge.md",
            upload_id="upload-1",
            raw_text="# Product\nProduct text.",
            file_size_bytes=len(b"# Product\nProduct text."),
        )
    )

    assert queue.payloads[0].processing_run_id
    assert (
        queue.payloads[0].processing_run_id
        == result.upload.processing_run.processing_run_id
    )
