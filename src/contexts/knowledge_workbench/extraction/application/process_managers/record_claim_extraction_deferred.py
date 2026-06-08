from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.events.artifact_events import ArtifactStored
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.entities.work_item_attempt import (
    WorkItemAttempt,
)
from src.contexts.execution_runtime.domain.events.work_item_events import (
    WorkItemDeferred,
)
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    WorkItemStateMachine,
)
from src.contexts.execution_runtime.domain.value_objects.wait_until import WaitUntil
from src.contexts.knowledge_workbench.extraction.application.ports.claim_extraction_work_item_unit_of_work_port import (
    ClaimExtractionWorkItemUnitOfWorkPort,
)
from src.contexts.llm_runtime.domain.entities.llm_attempt import LlmAttempt
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.events.llm_task_events import (
    LlmMinuteLimitHit,
    LlmTaskDeferred,
)
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind
from src.contexts.llm_runtime.domain.value_objects.llm_task_status import LlmTaskStatus


@dataclass(frozen=True, slots=True)
class RecordClaimExtractionDeferredCommand:
    leased_work_item: WorkItem
    work_item_attempt: WorkItemAttempt
    llm_task: LlmTask
    llm_attempt: LlmAttempt
    occurred_at: datetime
    error_artifact: PipelineArtifact | None = None

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        if self.llm_task.status is not LlmTaskStatus.DEFERRED:
            raise ValueError("llm_task must be DEFERRED")
        if self.llm_task.wait_until is None:
            raise ValueError("deferred llm_task must carry wait_until")
        if self.llm_task.last_error_kind is None:
            raise ValueError("deferred llm_task must carry last_error_kind")


@dataclass(frozen=True, slots=True)
class RecordClaimExtractionDeferredResult:
    deferred_work_item: WorkItem
    work_item_event: WorkItemDeferred
    llm_event: LlmTaskDeferred | LlmMinuteLimitHit
    error_artifact_event: ArtifactStored | None = None


class RecordClaimExtractionDeferred:
    """Atomically record deferred claim extraction runtime consequences.

    This is the key wait-state path for minute/rate limits: it releases the
    WorkItem lease and records a wait_until instead of relying on lease TTL.
    """

    def __init__(
        self,
        *,
        unit_of_work: ClaimExtractionWorkItemUnitOfWorkPort,
    ) -> None:
        self._unit_of_work = unit_of_work

    def execute(
        self,
        command: RecordClaimExtractionDeferredCommand,
    ) -> RecordClaimExtractionDeferredResult:
        error_kind = command.llm_task.last_error_kind
        if error_kind is None:
            raise ValueError("deferred llm_task must carry last_error_kind")

        wait_until = command.llm_task.wait_until
        if wait_until is None:
            raise ValueError("deferred llm_task must carry wait_until")

        deferred_work_item = WorkItemStateMachine.defer_leased(
            command.leased_work_item,
            wait_until=WaitUntil(wait_until),
            error_kind=error_kind.value,
        )

        work_item_event = WorkItemDeferred(
            work_item_id=deferred_work_item.work_item_id,
            wait_until=wait_until,
            error_kind=error_kind.value,
            occurred_at=command.occurred_at,
        )
        llm_event = _llm_deferred_event(
            task_id=command.llm_task.task_id,
            wait_until=wait_until,
            error_kind=error_kind,
            occurred_at=command.occurred_at,
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
            self._unit_of_work.save_work_item(deferred_work_item)
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

        return RecordClaimExtractionDeferredResult(
            deferred_work_item=deferred_work_item,
            work_item_event=work_item_event,
            llm_event=llm_event,
            error_artifact_event=error_artifact_event,
        )


def _llm_deferred_event(
    *,
    task_id: str,
    wait_until: datetime,
    error_kind: LlmErrorKind,
    occurred_at: datetime,
) -> LlmTaskDeferred | LlmMinuteLimitHit:
    if error_kind is LlmErrorKind.MINUTE_LIMIT:
        return LlmMinuteLimitHit(
            task_id=task_id,
            occurred_at=occurred_at,
            wait_until=wait_until,
        )

    return LlmTaskDeferred(
        task_id=task_id,
        occurred_at=occurred_at,
        wait_until=wait_until,
        error_kind=error_kind,
    )
