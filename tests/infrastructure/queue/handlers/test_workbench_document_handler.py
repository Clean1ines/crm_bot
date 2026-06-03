from __future__ import annotations

from dataclasses import dataclass

import pytest

from src.infrastructure.queue.handlers.workbench_document import (
    LegacyWorkbenchDocumentJobPayload,
    handle_process_workbench_document,
    mark_process_workbench_document_exhausted,
)
from src.infrastructure.queue.job_exceptions import PermanentJobError


@dataclass(frozen=True, slots=True)
class FakeJob:
    payload: dict[str, object]


def test_legacy_workbench_document_payload_requires_ids() -> None:
    payload = LegacyWorkbenchDocumentJobPayload.from_mapping(
        {
            "project_id": "project-1",
            "document_id": "document-1",
            "processing_run_id": "processing-run-1",
        }
    )

    assert payload.project_id == "project-1"
    assert payload.document_id == "document-1"
    assert payload.processing_run_id == "processing-run-1"


@pytest.mark.asyncio
async def test_process_workbench_document_handler_rejects_legacy_sequential_task() -> None:
    with pytest.raises(PermanentJobError, match="legacy process_workbench_document task is retired"):
        await handle_process_workbench_document(
            FakeJob(
                payload={
                    "project_id": "project-1",
                    "document_id": "document-1",
                    "processing_run_id": "processing-run-1",
                }
            ),
            connection=object(),
        )


@pytest.mark.asyncio
async def test_process_workbench_document_exhausted_hook_is_noop_for_retired_task() -> None:
    assert await mark_process_workbench_document_exhausted(
        FakeJob(
            payload={
                "project_id": "project-1",
                "document_id": "document-1",
                "processing_run_id": "processing-run-1",
            }
        )
    ) is None
