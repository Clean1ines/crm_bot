from __future__ import annotations

import pytest

from src.application.services.faq_workbench_fresh_upload_service import (
    MonotonicIdFactory,
)
from src.application.workbench.upload_service import (
    FaqWorkbenchUploadCommand,
    FaqWorkbenchUploadService,
)
from src.domain.project_plane.knowledge_workbench import SectionBatchQueueItemStatus
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

    assert repository.sections == list(result.upload.sections)
    assert len(repository.sections) == 2

    assert repository.registry_snapshots == [result.upload.initial_snapshot]

    assert repository.parallel_section_batch_plans == [
        result.upload.parallel_section_batch_plan
    ]
    assert len(repository.section_batch_queue_items) == len(result.upload.sections)
    assert result.upload.parallel_section_batch_plan.queue_items == tuple(
        repository.section_batch_queue_items
    )
    assert result.upload.parallel_section_batch_plan.max_lanes == 3
    assert result.upload.parallel_section_batch_plan.observed_registry_snapshot_id == (
        result.upload.initial_snapshot.snapshot_id
    )
    assert (
        result.upload.parallel_section_batch_plan.observed_registry_snapshot_sequence
        == (result.upload.initial_snapshot.sequence_number)
    )

    queue_item_ids = {
        item.queue_item_id for item in repository.section_batch_queue_items
    }
    assert len(queue_item_ids) == len(result.upload.sections)
    assert all(
        item.status is SectionBatchQueueItemStatus.READY
        for item in repository.section_batch_queue_items
    )
    assert all(
        item.observed_registry_snapshot_id == result.upload.initial_snapshot.snapshot_id
        for item in repository.section_batch_queue_items
    )
    assert all(
        item.observed_registry_snapshot_sequence
        == result.upload.initial_snapshot.sequence_number
        for item in repository.section_batch_queue_items
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
