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
    WorkItemSplitSuperseded,
)
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    WorkItemStateMachine,
)
from src.contexts.knowledge_workbench.extraction.application.ports.claim_extraction_work_item_unit_of_work_port import (
    ClaimExtractionWorkItemUnitOfWorkPort,
)
from src.contexts.llm_runtime.domain.entities.llm_attempt import LlmAttempt
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.events.llm_task_events import LlmTaskFailed
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind
from src.contexts.llm_runtime.domain.value_objects.llm_task_status import LlmTaskStatus


_SPLIT_ERROR_KINDS = {
    LlmErrorKind.REQUEST_TOO_LARGE,
    LlmErrorKind.OUTPUT_TOO_LARGE,
}


@dataclass(frozen=True, slots=True)
class RecordClaimExtractionSplitRequiredCommand:
    leased_work_item: WorkItem
    work_item_attempt: WorkItemAttempt
    llm_task: LlmTask
    llm_attempt: LlmAttempt
    split_artifact: PipelineArtifact
    occurred_at: datetime

    def __post_init__(self) -> None:
        if self.occurred_at.tzinfo is None or self.occurred_at.utcoffset() is None:
            raise ValueError("occurred_at must be timezone-aware")
        if self.llm_task.status not in {
            LlmTaskStatus.RETRYABLE_FAILED,
            LlmTaskStatus.TERMINAL_FAILED,
        }:
            raise ValueError(
                "split-required llm_task must be RETRYABLE_FAILED or TERMINAL_FAILED",
            )
        if self.llm_task.last_error_kind not in _SPLIT_ERROR_KINDS:
            raise ValueError(
                "split-required llm_task must carry REQUEST_TOO_LARGE or OUTPUT_TOO_LARGE",
            )


@dataclass(frozen=True, slots=True)
class RecordClaimExtractionSplitRequiredResult:
    superseded_work_item: WorkItem
    work_item_event: WorkItemSplitSuperseded
    llm_event: LlmTaskFailed
    split_artifact_event: ArtifactStored


class RecordClaimExtractionSplitRequired:
    """Atomically record that a claim extraction work item requires splitting.

    This process manager only records the parent work item as split-superseded
    and stores the split artifact. Creating child SourceUnits/WorkItems belongs
    to a later Source Management split workflow.
    """

    def __init__(
        self,
        *,
        unit_of_work: ClaimExtractionWorkItemUnitOfWorkPort,
    ) -> None:
        self._unit_of_work = unit_of_work

    def execute(
        self,
        command: RecordClaimExtractionSplitRequiredCommand,
    ) -> RecordClaimExtractionSplitRequiredResult:
        error_kind = command.llm_task.last_error_kind
        if error_kind not in _SPLIT_ERROR_KINDS:
            raise ValueError(
                "split-required llm_task must carry REQUEST_TOO_LARGE or OUTPUT_TOO_LARGE",
            )

        superseded_work_item = WorkItemStateMachine.mark_split_superseded_leased(
            command.leased_work_item,
        )

        work_item_event = WorkItemSplitSuperseded(
            work_item_id=superseded_work_item.work_item_id,
            occurred_at=command.occurred_at,
        )
        llm_event = LlmTaskFailed(
            task_id=command.llm_task.task_id,
            occurred_at=command.occurred_at,
            error_kind=error_kind,
        )
        split_artifact_event = ArtifactStored(
            artifact_ref=command.split_artifact.artifact_ref,
            occurred_at=command.occurred_at,
        )

        try:
            self._unit_of_work.save_work_item(superseded_work_item)
            self._unit_of_work.save_work_item_attempt(command.work_item_attempt)
            self._unit_of_work.save_llm_task(command.llm_task)
            self._unit_of_work.save_llm_attempt(command.llm_attempt)
            self._unit_of_work.save_artifact(command.split_artifact)
            self._unit_of_work.append_event(work_item_event)
            self._unit_of_work.append_event(llm_event)
            self._unit_of_work.append_event(split_artifact_event)
            self._unit_of_work.commit()
        except Exception:
            self._unit_of_work.rollback()
            raise

        return RecordClaimExtractionSplitRequiredResult(
            superseded_work_item=superseded_work_item,
            work_item_event=work_item_event,
            llm_event=llm_event,
            split_artifact_event=split_artifact_event,
        )
