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
    WorkItemUserActionRequired,
)
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    WorkItemStateMachine,
)
from src.contexts.knowledge_workbench.extraction.application.ports.claim_extraction_work_item_unit_of_work_port import (
    ClaimExtractionWorkItemUnitOfWorkPort,
)
from src.contexts.llm_runtime.domain.entities.llm_attempt import LlmAttempt
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.events.llm_task_events import (
    LlmDailyLimitExhausted,
)
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind
from src.contexts.llm_runtime.domain.value_objects.llm_task_status import LlmTaskStatus


DAILY_EXHAUSTED_DECISION_KIND = "continue_with_degraded_model_or_resume_next_day"


@dataclass(frozen=True, slots=True)
class RecordClaimExtractionDailyExhaustedCommand:
    leased_work_item: WorkItem
    work_item_attempt: WorkItemAttempt
    llm_task: LlmTask
    llm_attempt: LlmAttempt
    occurred_at: datetime
    error_artifact: PipelineArtifact | None = None

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        if self.llm_task.status is not LlmTaskStatus.RETRYABLE_FAILED:
            raise ValueError("daily exhausted llm_task must be RETRYABLE_FAILED")
        if self.llm_task.last_error_kind is not LlmErrorKind.DAILY_LIMIT:
            raise ValueError("daily exhausted llm_task must carry DAILY_LIMIT")


@dataclass(frozen=True, slots=True)
class RecordClaimExtractionDailyExhaustedResult:
    blocked_work_item: WorkItem
    work_item_event: WorkItemUserActionRequired
    llm_event: LlmDailyLimitExhausted
    error_artifact_event: ArtifactStored | None = None


class RecordClaimExtractionDailyExhausted:
    """Record daily exhaustion and require user decision.

    User choice is:
    continue with degraded llama instant route, or resume automatically after
    primary daily limits reset. This manager only records the blocked state and
    event; applying the user's choice is a separate command.
    """

    def __init__(
        self,
        *,
        unit_of_work: ClaimExtractionWorkItemUnitOfWorkPort,
    ) -> None:
        self._unit_of_work = unit_of_work

    def execute(
        self,
        command: RecordClaimExtractionDailyExhaustedCommand,
    ) -> RecordClaimExtractionDailyExhaustedResult:
        blocked_work_item = WorkItemStateMachine.require_user_action_leased(
            command.leased_work_item,
            error_kind=LlmErrorKind.DAILY_LIMIT.value,
        )
        work_item_event = WorkItemUserActionRequired(
            work_item_id=blocked_work_item.work_item_id,
            occurred_at=command.occurred_at,
            decision_kind=DAILY_EXHAUSTED_DECISION_KIND,
            reason=LlmErrorKind.DAILY_LIMIT.value,
        )
        llm_event = LlmDailyLimitExhausted(
            task_id=command.llm_task.task_id,
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
            self._unit_of_work.save_work_item(blocked_work_item)
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

        return RecordClaimExtractionDailyExhaustedResult(
            blocked_work_item=blocked_work_item,
            work_item_event=work_item_event,
            llm_event=llm_event,
            error_artifact_event=error_artifact_event,
        )
