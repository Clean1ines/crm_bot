from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    WorkItemStateMachine,
)
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)


class ClaimExtractionStageWorkItemReaderPort(Protocol):
    def load_work_items(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
    ) -> tuple[WorkItem, ...]: ...


class ClaimExtractionStageCancellationUnitOfWorkPort(Protocol):
    def save_work_item(self, item: WorkItem) -> None: ...

    def append_event(self, event: object) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...


@dataclass(frozen=True, slots=True)
class ClaimExtractionStageCancelled:
    workflow_run_id: str
    stage_run_id: str
    reason: str
    cancelled_by: str
    cancelled_count: int
    skipped_completed_count: int
    skipped_terminal_count: int
    occurred_at: datetime

    def __post_init__(self) -> None:
        _require_non_empty(self.workflow_run_id, "workflow_run_id")
        _require_non_empty(self.stage_run_id, "stage_run_id")
        _require_non_empty(self.reason, "reason")
        _require_non_empty(self.cancelled_by, "cancelled_by")
        _require_timezone_aware(self.occurred_at, "occurred_at")
        if self.cancelled_count < 0:
            raise ValueError("cancelled_count must be >= 0")
        if self.skipped_completed_count < 0:
            raise ValueError("skipped_completed_count must be >= 0")
        if self.skipped_terminal_count < 0:
            raise ValueError("skipped_terminal_count must be >= 0")


@dataclass(frozen=True, slots=True)
class CancelClaimExtractionStageCommand:
    workflow_run_id: str
    stage_run_id: str
    reason: str
    cancelled_by: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        _require_non_empty(self.workflow_run_id, "workflow_run_id")
        _require_non_empty(self.stage_run_id, "stage_run_id")
        _require_non_empty(self.reason, "reason")
        _require_non_empty(self.cancelled_by, "cancelled_by")
        _require_timezone_aware(self.occurred_at, "occurred_at")


@dataclass(frozen=True, slots=True)
class CancelClaimExtractionStageResult:
    cancelled_work_items: tuple[WorkItem, ...]
    event: ClaimExtractionStageCancelled
    skipped_completed_count: int
    skipped_terminal_count: int


class CancelClaimExtractionStage:
    """Cancel runnable claim-extraction WorkItems without touching artifacts."""

    def __init__(
        self,
        *,
        reader: ClaimExtractionStageWorkItemReaderPort,
        unit_of_work: ClaimExtractionStageCancellationUnitOfWorkPort,
    ) -> None:
        self._reader = reader
        self._unit_of_work = unit_of_work

    def execute(
        self,
        command: CancelClaimExtractionStageCommand,
    ) -> CancelClaimExtractionStageResult:
        work_items = self._reader.load_work_items(
            workflow_run_id=command.workflow_run_id,
            stage_run_id=command.stage_run_id,
        )

        cancelled_items: list[WorkItem] = []
        skipped_completed_count = 0
        skipped_terminal_count = 0

        for item in work_items:
            if item.status is WorkItemStatus.COMPLETED:
                skipped_completed_count += 1
                continue

            if item.status in {
                WorkItemStatus.TERMINAL_FAILED,
                WorkItemStatus.CANCELLED,
                WorkItemStatus.SPLIT_SUPERSEDED,
            }:
                skipped_terminal_count += 1
                continue

            if item.status in {
                WorkItemStatus.READY,
                WorkItemStatus.LEASED,
                WorkItemStatus.DEFERRED,
                WorkItemStatus.USER_ACTION_REQUIRED,
            }:
                cancelled_items.append(_cancel_item(item, reason=command.reason))

        event = ClaimExtractionStageCancelled(
            workflow_run_id=command.workflow_run_id,
            stage_run_id=command.stage_run_id,
            reason=command.reason,
            cancelled_by=command.cancelled_by,
            cancelled_count=len(cancelled_items),
            skipped_completed_count=skipped_completed_count,
            skipped_terminal_count=skipped_terminal_count,
            occurred_at=command.occurred_at,
        )

        try:
            for item in cancelled_items:
                self._unit_of_work.save_work_item(item)
            self._unit_of_work.append_event(event)
            self._unit_of_work.commit()
        except Exception:
            self._unit_of_work.rollback()
            raise

        return CancelClaimExtractionStageResult(
            cancelled_work_items=tuple(cancelled_items),
            event=event,
            skipped_completed_count=skipped_completed_count,
            skipped_terminal_count=skipped_terminal_count,
        )


def _cancel_item(item: WorkItem, *, reason: str) -> WorkItem:
    return WorkItemStateMachine.cancel(item, error_kind=reason)


def _require_non_empty(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
