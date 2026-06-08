from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.events.artifact_events import ArtifactStored
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.entities.work_item_attempt import (
    WorkItemAttempt,
)
from src.contexts.execution_runtime.domain.events.work_item_events import WorkItemFailed
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    WorkItemStateMachine,
)
from src.contexts.execution_runtime.domain.value_objects.wait_until import WaitUntil
from src.contexts.knowledge_workbench.extraction.application.ports.claim_extraction_work_item_unit_of_work_port import (
    ClaimExtractionWorkItemUnitOfWorkPort,
)
from src.contexts.llm_runtime.domain.entities.llm_attempt import LlmAttempt
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.events.llm_task_events import LlmTaskFailed
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind
from src.contexts.llm_runtime.domain.value_objects.llm_task_status import LlmTaskStatus


class ClaimExtractionFailureMode(StrEnum):
    RETRYABLE = "retryable"
    TERMINAL = "terminal"


@dataclass(frozen=True, slots=True)
class RecordClaimExtractionFailedCommand:
    leased_work_item: WorkItem
    work_item_attempt: WorkItemAttempt
    llm_task: LlmTask
    llm_attempt: LlmAttempt
    mode: ClaimExtractionFailureMode
    occurred_at: datetime
    next_attempt_at: WaitUntil | None = None
    error_artifact: PipelineArtifact | None = None

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        if self.llm_task.last_error_kind is None:
            raise ValueError("failed llm_task must carry last_error_kind")
        if self.mode is ClaimExtractionFailureMode.RETRYABLE:
            if self.llm_task.status is not LlmTaskStatus.RETRYABLE_FAILED:
                raise ValueError("retryable failure requires RETRYABLE_FAILED llm_task")
            if self.next_attempt_at is None:
                raise ValueError("retryable failure requires next_attempt_at")
        if self.mode is ClaimExtractionFailureMode.TERMINAL:
            if self.llm_task.status is not LlmTaskStatus.TERMINAL_FAILED:
                raise ValueError("terminal failure requires TERMINAL_FAILED llm_task")
            if self.next_attempt_at is not None:
                raise ValueError("terminal failure must not have next_attempt_at")


@dataclass(frozen=True, slots=True)
class RecordClaimExtractionFailedResult:
    failed_work_item: WorkItem
    work_item_event: WorkItemFailed
    llm_event: LlmTaskFailed
    error_artifact_event: ArtifactStored | None = None


class RecordClaimExtractionFailed:
    """Atomically record failed claim extraction runtime consequences.

    This process manager covers retryable and terminal failures only.
    Daily exhaustion and split-required decisions remain separate workflow paths.
    """

    def __init__(
        self,
        *,
        unit_of_work: ClaimExtractionWorkItemUnitOfWorkPort,
    ) -> None:
        self._unit_of_work = unit_of_work

    def execute(
        self,
        command: RecordClaimExtractionFailedCommand,
    ) -> RecordClaimExtractionFailedResult:
        error_kind = command.llm_task.last_error_kind
        if error_kind is None:
            raise ValueError("failed llm_task must carry last_error_kind")

        failed_work_item = _fail_work_item(command=command, error_kind=error_kind)

        work_item_event = WorkItemFailed(
            work_item_id=failed_work_item.work_item_id,
            status=failed_work_item.status,
            error_kind=error_kind.value,
            occurred_at=command.occurred_at,
        )
        llm_event = LlmTaskFailed(
            task_id=command.llm_task.task_id,
            occurred_at=command.occurred_at,
            error_kind=error_kind,
        )
        error_artifact_event = (
            ArtifactStored(
                artifact_ref=command.error_artifact.artifact_ref,
                occurred_at=command.occurred_at,
            )
            if command.error_artifact is not None
            else None
        )

        try:
            self._unit_of_work.save_work_item(failed_work_item)
            self._unit_of_work.save_work_item_attempt(command.work_item_attempt)
            self._unit_of_work.save_llm_task(command.llm_task)
            self._unit_of_work.save_llm_attempt(command.llm_attempt)
            if command.error_artifact is not None:
                self._unit_of_work.save_artifact(command.error_artifact)
            self._unit_of_work.append_event(work_item_event)
            self._unit_of_work.append_event(llm_event)
            if error_artifact_event is not None:
                self._unit_of_work.append_event(error_artifact_event)
            self._unit_of_work.commit()
        except Exception:
            self._unit_of_work.rollback()
            raise

        return RecordClaimExtractionFailedResult(
            failed_work_item=failed_work_item,
            work_item_event=work_item_event,
            llm_event=llm_event,
            error_artifact_event=error_artifact_event,
        )


def _fail_work_item(
    *,
    command: RecordClaimExtractionFailedCommand,
    error_kind: LlmErrorKind,
) -> WorkItem:
    if command.mode is ClaimExtractionFailureMode.RETRYABLE:
        if command.next_attempt_at is None:
            raise ValueError("retryable failure requires next_attempt_at")
        return WorkItemStateMachine.fail_leased_retryable(
            command.leased_work_item,
            error_kind=error_kind.value,
            next_attempt_at=command.next_attempt_at,
        )

    return WorkItemStateMachine.fail_leased_terminal(
        command.leased_work_item,
        error_kind=error_kind.value,
    )
