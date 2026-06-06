from __future__ import annotations

from collections.abc import Mapping

import pytest

from src.domain.project_plane.knowledge_workbench import DomainInvariantError
from src.infrastructure.queue.handlers import (
    workbench_parallel_processing_terminal as terminal,
)
from src.infrastructure.queue.handlers.workbench_parallel_processing import (
    WorkbenchParallelProcessingJobPayloadDto,
)
from src.infrastructure.queue.job_exceptions import PermanentJobError, TransientJobError


class FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    async def execute(self, query: str, *args: object) -> str:
        self.calls.append((query, args))
        return "UPDATE 1"


async def _raise_prompt_contract_failure(
    *,
    payload: WorkbenchParallelProcessingJobPayloadDto | Mapping[str, object],
    connection: object,
) -> object:
    raise DomainInvariantError(
        "claim observation #7 requires non-empty string evidence_block"
    )


async def _raise_payload_domain_failure(
    *,
    payload: WorkbenchParallelProcessingJobPayloadDto | Mapping[str, object],
    connection: object,
) -> object:
    raise DomainInvariantError("parallel queue payload requires project_id")


@pytest.mark.asyncio
async def test_prompt_a_output_contract_error_is_retryable_without_marking_document_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection()
    monkeypatch.setattr(
        terminal,
        "handle_workbench_parallel_processing_job_from_connection",
        _raise_prompt_contract_failure,
    )

    with pytest.raises(
        TransientJobError, match="retryable Prompt A output contract failure"
    ):
        await terminal.handle_workbench_parallel_processing_job_terminal(
            payload={
                "project_id": "0f36f58c-fc0d-4741-bff0-9de6e330ebe1",
                "document_id": "document-1",
                "processing_run_id": "run-1",
            },
            connection=connection,
        )

    assert connection.calls == []


@pytest.mark.asyncio
async def test_non_prompt_a_domain_error_remains_permanent_and_marks_document_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = FakeConnection()
    monkeypatch.setattr(
        terminal,
        "handle_workbench_parallel_processing_job_from_connection",
        _raise_payload_domain_failure,
    )

    with pytest.raises(
        PermanentJobError, match="parallel queue payload requires project_id"
    ):
        await terminal.handle_workbench_parallel_processing_job_terminal(
            payload={
                "project_id": "0f36f58c-fc0d-4741-bff0-9de6e330ebe1",
                "document_id": "document-1",
                "processing_run_id": "run-1",
            },
            connection=connection,
        )

    assert len(connection.calls) == 2
    sql = "\\n".join(query for query, _ in connection.calls)
    assert "UPDATE knowledge_workbench_processing_runs" in sql
    assert "UPDATE knowledge_workbench_documents" in sql
