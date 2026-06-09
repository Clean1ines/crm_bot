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
from src.contexts.knowledge_workbench.extraction.application.policies.claim_extraction_artifact_provenance import (
    ClaimExtractionArtifactProvenance,
    InvalidClaimExtractionArtifactProvenance,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_extraction_prompt_a_artifact_factory import (
    PROMPT_A_PARSED_CLAIM_OBSERVATIONS_ARTIFACT_KIND,
    PROMPT_A_RAW_CLAIM_OBSERVATIONS_ARTIFACT_KIND,
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
        _require_factory_created_prompt_a_artifact_pair(
            raw_artifact=self.raw_output_artifact,
            parsed_artifact=self.parsed_output_artifact,
            llm_task=self.llm_task,
            llm_attempt=self.llm_attempt,
            work_item=self.leased_work_item,
            work_item_attempt=self.work_item_attempt,
        )


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


def _require_factory_created_prompt_a_artifact_pair(
    *,
    raw_artifact: PipelineArtifact,
    parsed_artifact: PipelineArtifact,
    llm_task: LlmTask,
    llm_attempt: LlmAttempt,
    work_item: WorkItem,
    work_item_attempt: WorkItemAttempt,
) -> None:
    if raw_artifact.artifact_kind != PROMPT_A_RAW_CLAIM_OBSERVATIONS_ARTIFACT_KIND:
        raise ValueError("raw_output_artifact must use Prompt A raw artifact kind")
    if (
        parsed_artifact.artifact_kind
        != PROMPT_A_PARSED_CLAIM_OBSERVATIONS_ARTIFACT_KIND
    ):
        raise ValueError(
            "parsed_output_artifact must use Prompt A parsed artifact kind"
        )
    if parsed_artifact.lineage.parent_refs != (raw_artifact.artifact_ref,):
        raise ValueError(
            "parsed_output_artifact must have raw_output_artifact as sole parent"
        )

    try:
        raw_provenance = (
            ClaimExtractionArtifactProvenance.from_raw_artifact_payload_fields(
                raw_artifact.payload.value,
            )
        )
        parsed_provenance = (
            ClaimExtractionArtifactProvenance.from_parsed_artifact_payload_fields(
                parsed_artifact.payload.value,
            )
        )
    except InvalidClaimExtractionArtifactProvenance as exc:
        raise ValueError(str(exc)) from exc

    if raw_provenance != parsed_provenance:
        raise ValueError("raw and parsed artifact provenance must match")
    if raw_provenance.work_item_id != work_item.work_item_id:
        raise ValueError("artifact provenance work_item_id must match WorkItem")
    if raw_provenance.work_item_attempt_id != work_item_attempt.attempt_id:
        raise ValueError(
            "artifact provenance work_item_attempt_id must match WorkItemAttempt"
        )
    if raw_provenance.llm_task_id != llm_task.task_id:
        raise ValueError("artifact provenance llm_task_id must match LlmTask")
    if raw_provenance.llm_attempt_id != llm_attempt.attempt_id:
        raise ValueError("artifact provenance llm_attempt_id must match LlmAttempt")
    if raw_provenance.prompt_id != llm_task.prompt_id:
        raise ValueError("artifact provenance prompt_id must match LlmTask")
    if raw_provenance.prompt_version != llm_task.prompt_version.value:
        raise ValueError("artifact provenance prompt_version must match LlmTask")
    parsed_raw_ref_value = parsed_artifact.payload.value.get("raw_artifact_ref")
    if parsed_raw_ref_value != raw_artifact.artifact_ref.value:
        raise ValueError("parsed artifact raw_artifact_ref must match raw artifact ref")
