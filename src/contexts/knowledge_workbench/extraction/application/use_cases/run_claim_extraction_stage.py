from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from src.contexts.execution_runtime.application.ports.work_item_unit_of_work_port import (
    WorkItemUnitOfWorkPort,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
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


class ClaimExtractionWorkItemCreatorPort(Protocol):
    def execute(
        self,
        command: CreateExtractionWorkItemsCommand,
    ) -> object: ...


class ClaimExtractionStageWorkItemIndexPort(Protocol):
    def save_stage_work_item(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
        work_item: WorkItem,
    ) -> None: ...


class ClaimExtractionStageStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    WAITING_FOR_QUOTA = "waiting_for_quota"
    USER_ACTION_REQUIRED = "user_action_required"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class RunClaimExtractionStageCommand:
    workflow_run_id: str
    stage_run_id: str
    source_units: tuple[SourceUnit, ...]
    prompt_id: str

    def __post_init__(self) -> None:
        _require_non_empty(self.workflow_run_id, "workflow_run_id")
        _require_non_empty(self.stage_run_id, "stage_run_id")
        if not self.source_units:
            raise ValueError("source_units must be non-empty")
        _require_non_empty(self.prompt_id, "prompt_id")


@dataclass(frozen=True, slots=True)
class ClaimExtractionStageReadiness:
    status: ClaimExtractionStageStatus
    total_count: int
    ready_count: int
    leased_count: int
    deferred_count: int
    retryable_failed_count: int
    user_action_required_count: int
    completed_count: int
    terminal_failed_count: int
    cancelled_count: int
    split_superseded_count: int


@dataclass(frozen=True, slots=True)
class RunClaimExtractionStageResult:
    work_items: tuple[WorkItem, ...]
    readiness: ClaimExtractionStageReadiness


class RunClaimExtractionStage:
    """Create claim-extraction work items and report stage readiness.

    This is the application-level fan-out entry point for Prompt A extraction.
    It does not lease work, execute LLM calls, write DB directly, or touch legacy queues.
    """

    def __init__(
        self,
        *,
        unit_of_work: WorkItemUnitOfWorkPort,
        stage_work_item_index: ClaimExtractionStageWorkItemIndexPort,
        work_item_creator: ClaimExtractionWorkItemCreatorPort | None = None,
    ) -> None:
        self._unit_of_work = unit_of_work
        self._stage_work_item_index = stage_work_item_index
        self._work_item_creator = work_item_creator or CreateExtractionWorkItems()

    def execute(
        self,
        command: RunClaimExtractionStageCommand,
    ) -> RunClaimExtractionStageResult:
        created = self._work_item_creator.execute(
            CreateExtractionWorkItemsCommand(
                source_units=command.source_units,
                prompt_id=command.prompt_id,
            ),
        )
        work_items = _created_work_items(created)

        try:
            for item in work_items:
                self._unit_of_work.save_work_item(item)
                self._stage_work_item_index.save_stage_work_item(
                    workflow_run_id=command.workflow_run_id,
                    stage_run_id=command.stage_run_id,
                    work_item=item,
                )
            self._unit_of_work.commit()
        except Exception:
            self._unit_of_work.rollback()
            raise

        return RunClaimExtractionStageResult(
            work_items=work_items,
            readiness=claim_extraction_stage_readiness(work_items),
        )


def claim_extraction_stage_readiness(
    work_items: tuple[WorkItem, ...],
) -> ClaimExtractionStageReadiness:
    if not work_items:
        raise ValueError("work_items must be non-empty")

    ready_count = _count_status(work_items, WorkItemStatus.READY)
    leased_count = _count_status(work_items, WorkItemStatus.LEASED)
    deferred_count = _count_status(work_items, WorkItemStatus.DEFERRED)
    retryable_failed_count = _count_status(work_items, WorkItemStatus.RETRYABLE_FAILED)
    user_action_required_count = _count_status(
        work_items,
        WorkItemStatus.USER_ACTION_REQUIRED,
    )
    completed_count = _count_status(work_items, WorkItemStatus.COMPLETED)
    terminal_failed_count = _count_status(work_items, WorkItemStatus.TERMINAL_FAILED)
    cancelled_count = _count_status(work_items, WorkItemStatus.CANCELLED)
    split_superseded_count = _count_status(work_items, WorkItemStatus.SPLIT_SUPERSEDED)

    status = _stage_status(
        total_count=len(work_items),
        ready_count=ready_count,
        leased_count=leased_count,
        deferred_count=deferred_count,
        retryable_failed_count=retryable_failed_count,
        user_action_required_count=user_action_required_count,
        completed_count=completed_count,
        terminal_failed_count=terminal_failed_count,
        cancelled_count=cancelled_count,
        split_superseded_count=split_superseded_count,
    )

    return ClaimExtractionStageReadiness(
        status=status,
        total_count=len(work_items),
        ready_count=ready_count,
        leased_count=leased_count,
        deferred_count=deferred_count,
        retryable_failed_count=retryable_failed_count,
        user_action_required_count=user_action_required_count,
        completed_count=completed_count,
        terminal_failed_count=terminal_failed_count,
        cancelled_count=cancelled_count,
        split_superseded_count=split_superseded_count,
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


def _count_status(
    work_items: tuple[WorkItem, ...],
    status: WorkItemStatus,
) -> int:
    return sum(1 for item in work_items if item.status is status)


def _stage_status(
    *,
    total_count: int,
    ready_count: int,
    leased_count: int,
    deferred_count: int,
    retryable_failed_count: int,
    user_action_required_count: int,
    completed_count: int,
    terminal_failed_count: int,
    cancelled_count: int,
    split_superseded_count: int,
) -> ClaimExtractionStageStatus:
    if terminal_failed_count > 0 or cancelled_count > 0:
        return ClaimExtractionStageStatus.FAILED

    if user_action_required_count > 0:
        return ClaimExtractionStageStatus.USER_ACTION_REQUIRED

    if deferred_count > 0 or retryable_failed_count > 0:
        return ClaimExtractionStageStatus.WAITING_FOR_QUOTA

    if leased_count > 0:
        return ClaimExtractionStageStatus.IN_PROGRESS

    completed_or_superseded = completed_count + split_superseded_count
    if completed_or_superseded == total_count:
        return ClaimExtractionStageStatus.COMPLETED

    if ready_count > 0:
        return ClaimExtractionStageStatus.PENDING

    return ClaimExtractionStageStatus.IN_PROGRESS


def _require_non_empty(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
