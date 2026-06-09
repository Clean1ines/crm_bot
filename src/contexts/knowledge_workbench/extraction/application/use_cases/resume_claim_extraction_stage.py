from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_status import (
    ArtifactStatus,
)
from src.contexts.execution_runtime.application.ports.work_item_unit_of_work_port import (
    WorkItemUnitOfWorkPort,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    WorkItemStateMachine,
)
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.knowledge_workbench.extraction.application.use_cases.create_extraction_work_items import (
    CreateExtractionWorkItems,
    CreateExtractionWorkItemsCommand,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)


class ClaimExtractionResumeWorkItemCreatorPort(Protocol):
    def execute(self, command: CreateExtractionWorkItemsCommand) -> object: ...


class ClaimExtractionStageResumeReaderPort(Protocol):
    def load_completed_artifacts(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
    ) -> tuple[ClaimExtractionStageArtifactRecord, ...]: ...

    def load_work_items(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
    ) -> tuple[WorkItem, ...]: ...


@dataclass(frozen=True, slots=True)
class ClaimExtractionStageArtifactRecord:
    artifact: PipelineArtifact
    work_item_id: str
    source_unit_ref: str

    def __post_init__(self) -> None:
        if not self.work_item_id or not self.work_item_id.strip():
            raise ValueError("work_item_id must be non-empty")
        if not self.source_unit_ref or not self.source_unit_ref.strip():
            raise ValueError("source_unit_ref must be non-empty")


@dataclass(frozen=True, slots=True)
class ResumeClaimExtractionStageCommand:
    workflow_run_id: str
    stage_run_id: str
    source_units: tuple[SourceUnit, ...]
    prompt_id: str
    now: datetime
    recreate_missing: bool = True
    return_retryable_to_ready: bool = True
    return_due_deferred_to_ready: bool = True

    def __post_init__(self) -> None:
        if not self.workflow_run_id or not self.workflow_run_id.strip():
            raise ValueError("workflow_run_id must be non-empty")
        if not self.stage_run_id or not self.stage_run_id.strip():
            raise ValueError("stage_run_id must be non-empty")
        if not self.source_units:
            raise ValueError("source_units must be non-empty")
        if not self.prompt_id or not self.prompt_id.strip():
            raise ValueError("prompt_id must be non-empty")
        if self.now.tzinfo is None or self.now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ClaimExtractionResumeSummary:
    completed_count: int
    ready_count: int
    deferred_count: int
    missing_count: int
    recreated_count: int
    blocked_reason: str | None = None


@dataclass(frozen=True, slots=True)
class ResumeClaimExtractionStageResult:
    summary: ClaimExtractionResumeSummary
    saved_work_items: tuple[WorkItem, ...]


class ResumeClaimExtractionStage:
    """Resume claim extraction stage from canonical WorkItems and artifacts."""

    def __init__(
        self,
        *,
        reader: ClaimExtractionStageResumeReaderPort,
        unit_of_work: WorkItemUnitOfWorkPort,
        work_item_creator: ClaimExtractionResumeWorkItemCreatorPort | None = None,
    ) -> None:
        self._reader = reader
        self._unit_of_work = unit_of_work
        self._work_item_creator = work_item_creator or CreateExtractionWorkItems()

    def execute(
        self,
        command: ResumeClaimExtractionStageCommand,
    ) -> ResumeClaimExtractionStageResult:
        artifacts = self._reader.load_completed_artifacts(
            workflow_run_id=command.workflow_run_id,
            stage_run_id=command.stage_run_id,
        )
        existing_work_items = self._reader.load_work_items(
            workflow_run_id=command.workflow_run_id,
            stage_run_id=command.stage_run_id,
        )
        expected_work_items = _created_work_items(
            self._work_item_creator.execute(
                CreateExtractionWorkItemsCommand(
                    source_units=command.source_units,
                    prompt_id=command.prompt_id,
                ),
            ),
        )

        completed_artifacts_by_work_item_id = _completed_artifacts_by_work_item_id(
            artifacts,
        )
        existing_by_id = {item.work_item_id: item for item in existing_work_items}

        completed_count = 0
        ready_count = 0
        deferred_count = 0
        missing_count = 0
        recreated: list[WorkItem] = []
        blocked_reason: str | None = None

        for expected_item in expected_work_items:
            completed_artifact = completed_artifacts_by_work_item_id.get(
                expected_item.work_item_id,
            )
            existing_item = existing_by_id.get(expected_item.work_item_id)

            if completed_artifact is not None:
                completed_count += 1
                if existing_item is not None and existing_item.status in {
                    WorkItemStatus.CANCELLED,
                    WorkItemStatus.TERMINAL_FAILED,
                }:
                    blocked_reason = (
                        blocked_reason or "terminal_or_cancelled_completed_item"
                    )
                continue

            if existing_item is None:
                missing_count += 1
                if command.recreate_missing:
                    recreated.append(expected_item)
                    ready_count += 1
                continue

            if existing_item.status is WorkItemStatus.READY:
                ready_count += 1
                continue

            if existing_item.status is WorkItemStatus.COMPLETED:
                blocked_reason = (
                    blocked_reason or "completed_work_item_missing_artifact"
                )
                continue

            if existing_item.status is WorkItemStatus.LEASED:
                recreated.append(
                    WorkItemStateMachine.release_leased_to_ready(
                        existing_item,
                        reason="resume_released_lease",
                    ),
                )
                ready_count += 1
                continue

            if existing_item.status is WorkItemStatus.DEFERRED:
                if _deferred_waits_in_future(existing_item, command.now):
                    deferred_count += 1
                    continue
                if command.return_due_deferred_to_ready:
                    recreated.append(_ready_copy(existing_item))
                    ready_count += 1
                else:
                    deferred_count += 1
                continue

            if existing_item.status is WorkItemStatus.RETRYABLE_FAILED:
                if command.return_retryable_to_ready:
                    recreated.append(_ready_copy(existing_item))
                    ready_count += 1
                else:
                    deferred_count += 1
                continue

            if existing_item.status in {
                WorkItemStatus.CANCELLED,
                WorkItemStatus.TERMINAL_FAILED,
            }:
                blocked_reason = blocked_reason or "terminal_or_cancelled_work_item"
                continue

            if existing_item.status is WorkItemStatus.USER_ACTION_REQUIRED:
                blocked_reason = blocked_reason or "user_action_required_work_item"
                continue

            if existing_item.status is WorkItemStatus.SPLIT_SUPERSEDED:
                completed_count += 1
                continue

        try:
            for item in recreated:
                self._unit_of_work.save_work_item(item)
            if recreated:
                self._unit_of_work.commit()
        except Exception:
            self._unit_of_work.rollback()
            raise

        return ResumeClaimExtractionStageResult(
            summary=ClaimExtractionResumeSummary(
                completed_count=completed_count,
                ready_count=ready_count,
                deferred_count=deferred_count,
                missing_count=missing_count,
                recreated_count=len(recreated),
                blocked_reason=blocked_reason,
            ),
            saved_work_items=tuple(recreated),
        )


def _created_work_items(created: object) -> tuple[WorkItem, ...]:
    work_items = getattr(created, "work_items", None)
    if not isinstance(work_items, tuple):
        raise TypeError("work_item_creator result must expose tuple work_items")
    if not all(isinstance(item, WorkItem) for item in work_items):
        raise TypeError("work_item_creator work_items must contain only WorkItem")
    if not work_items:
        raise ValueError("work_item_creator returned no work items")
    return work_items


def _completed_artifacts_by_work_item_id(
    records: tuple[ClaimExtractionStageArtifactRecord, ...],
) -> dict[str, PipelineArtifact]:
    completed: dict[str, PipelineArtifact] = {}
    for record in records:
        if record.artifact.status in {
            ArtifactStatus.REJECTED,
            ArtifactStatus.SUPERSEDED,
            ArtifactStatus.EXPIRED,
        }:
            continue
        completed[record.work_item_id] = record.artifact
    return completed


def _deferred_waits_in_future(item: WorkItem, now: datetime) -> bool:
    return item.next_attempt_at is not None and item.next_attempt_at.value > now


def _ready_copy(item: WorkItem) -> WorkItem:
    return WorkItem(
        work_item_id=item.work_item_id,
        work_kind=item.work_kind,
        status=WorkItemStatus.READY,
        attempt_count=item.attempt_count,
    )
