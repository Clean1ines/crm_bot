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
    WorkItemCompleted,
)
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    WorkItemStateMachine,
)
from src.contexts.knowledge_workbench.extraction.application.ports.claim_extraction_work_item_unit_of_work_port import (
    ClaimExtractionWorkItemUnitOfWorkPort,
)
from src.contexts.llm_runtime.domain.entities.llm_attempt import LlmAttempt
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.events.llm_task_events import LlmTaskSucceeded
from src.contexts.llm_runtime.domain.value_objects.llm_task_status import LlmTaskStatus


@dataclass(frozen=True, slots=True)
class RecordClaimExtractionSuccessCommand:
    leased_work_item: WorkItem
    work_item_attempt: WorkItemAttempt
    llm_task: LlmTask
    llm_attempt: LlmAttempt
    raw_output_artifact: PipelineArtifact
    parsed_output_artifact: PipelineArtifact
    occurred_at: datetime

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        if self.llm_task.status is not LlmTaskStatus.SUCCEEDED:
            raise ValueError("llm_task must be SUCCEEDED")


@dataclass(frozen=True, slots=True)
class RecordClaimExtractionSuccessResult:
    completed_work_item: WorkItem
    work_item_event: WorkItemCompleted
    llm_event: LlmTaskSucceeded
    raw_artifact_event: ArtifactStored
    parsed_artifact_event: ArtifactStored


class RecordClaimExtractionSuccess:
    """Atomically record successful claim extraction runtime consequences."""

    def __init__(
        self,
        *,
        unit_of_work: ClaimExtractionWorkItemUnitOfWorkPort,
    ) -> None:
        self._unit_of_work = unit_of_work

    def execute(
        self,
        command: RecordClaimExtractionSuccessCommand,
    ) -> RecordClaimExtractionSuccessResult:
        completed_work_item = WorkItemStateMachine.complete_leased(
            command.leased_work_item,
        )

        work_item_event = WorkItemCompleted(
            work_item_id=completed_work_item.work_item_id,
            occurred_at=command.occurred_at,
        )
        llm_event = LlmTaskSucceeded(
            task_id=command.llm_task.task_id,
            occurred_at=command.occurred_at,
        )
        raw_artifact_event = ArtifactStored(
            artifact_ref=command.raw_output_artifact.artifact_ref,
            occurred_at=command.occurred_at,
        )
        parsed_artifact_event = ArtifactStored(
            artifact_ref=command.parsed_output_artifact.artifact_ref,
            occurred_at=command.occurred_at,
        )

        try:
            self._unit_of_work.save_work_item(completed_work_item)
            self._unit_of_work.save_work_item_attempt(command.work_item_attempt)
            self._unit_of_work.save_llm_task(command.llm_task)
            self._unit_of_work.save_llm_attempt(command.llm_attempt)
            self._unit_of_work.save_artifact(command.raw_output_artifact)
            self._unit_of_work.save_artifact(command.parsed_output_artifact)
            self._unit_of_work.append_event(work_item_event)
            self._unit_of_work.append_event(llm_event)
            self._unit_of_work.append_event(raw_artifact_event)
            self._unit_of_work.append_event(parsed_artifact_event)
            self._unit_of_work.commit()
        except Exception:
            self._unit_of_work.rollback()
            raise

        return RecordClaimExtractionSuccessResult(
            completed_work_item=completed_work_item,
            work_item_event=work_item_event,
            llm_event=llm_event,
            raw_artifact_event=raw_artifact_event,
            parsed_artifact_event=parsed_artifact_event,
        )
