from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from src.contexts.execution_runtime.application.ports.work_item_attempt_outcome_repository_port import (
    WorkItemAttemptOutcomeRecord,
    WorkItemAttemptOutcomeRepositoryPort,
    WorkItemAttemptOutcomeStatus,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_item_retry_plan import (
    WorkItemRetryPlan,
)


@dataclass(frozen=True, slots=True)
class RecordWorkItemAttemptOutcomeCommand:
    attempt_id: str
    work_item_id: str
    attempt_number: int
    lease_token: LeaseToken
    finished_at: datetime
    outcome_status: WorkItemAttemptOutcomeStatus
    error_kind: str | None = None
    next_attempt_at: datetime | None = None
    retry_plan: WorkItemRetryPlan | None = None
    validation_metadata: Mapping[str, object] | None = None
    llm_output_payload: Mapping[str, object] | None = None


@dataclass(frozen=True, slots=True)
class RecordWorkItemAttemptOutcomeResult:
    work_item: WorkItem


@dataclass(frozen=True, slots=True)
class RecordWorkItemAttemptOutcome:
    repository: WorkItemAttemptOutcomeRepositoryPort

    async def execute(
        self,
        command: RecordWorkItemAttemptOutcomeCommand,
    ) -> RecordWorkItemAttemptOutcomeResult:
        record = WorkItemAttemptOutcomeRecord(
            attempt_id=command.attempt_id,
            work_item_id=command.work_item_id,
            attempt_number=command.attempt_number,
            lease_token=command.lease_token,
            finished_at=command.finished_at,
            outcome_status=command.outcome_status,
            error_kind=command.error_kind,
            next_attempt_at=command.next_attempt_at,
            retry_plan=command.retry_plan,
            validation_metadata=command.validation_metadata,
            llm_output_payload=command.llm_output_payload,
        )
        work_item = await self.repository.record_attempt_outcome(record)
        return RecordWorkItemAttemptOutcomeResult(work_item=work_item)
