from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.wait_until import WaitUntil
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.knowledge_workbench.extraction.application.use_cases.cancel_claim_extraction_stage import (
    CancelClaimExtractionStage,
    CancelClaimExtractionStageCommand,
    ClaimExtractionStageCancelled,
)


@dataclass(slots=True)
class FakeStageWorkItemReader:
    work_items: tuple[WorkItem, ...]
    queries: list[tuple[str, str]] = field(default_factory=list)

    def load_work_items(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
    ) -> tuple[WorkItem, ...]:
        self.queries.append((workflow_run_id, stage_run_id))
        return self.work_items


@dataclass(slots=True)
class FakeStageCancellationUnitOfWork:
    saved_work_items: list[WorkItem] = field(default_factory=list)
    events: list[object] = field(default_factory=list)
    committed_count: int = 0
    rolled_back_count: int = 0
    fail_on_save: bool = False

    def save_work_item(self, item: WorkItem) -> None:
        if self.fail_on_save:
            raise RuntimeError("save failed")
        self.saved_work_items.append(item)

    def append_event(self, event: object) -> None:
        self.events.append(event)

    def commit(self) -> None:
        self.committed_count += 1

    def rollback(self) -> None:
        self.rolled_back_count += 1


@dataclass(slots=True)
class FakeArtifactRepository:
    deleted_refs: list[str] = field(default_factory=list)

    def delete_artifact(self, artifact_ref: str) -> None:
        self.deleted_refs.append(artifact_ref)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _work_item(
    item_id: str,
    *,
    status: WorkItemStatus,
) -> WorkItem:
    if status is WorkItemStatus.LEASED:
        return WorkItem(
            work_item_id=item_id,
            work_kind=WorkKind("knowledge_workbench.claim_extraction"),
            status=status,
            attempt_count=1,
            leased_by=WorkerRef("worker-1"),
            lease_token=LeaseToken("lease-1"),
            lease_expires_at=_now() + timedelta(minutes=5),
        )

    if status is WorkItemStatus.DEFERRED:
        return WorkItem(
            work_item_id=item_id,
            work_kind=WorkKind("knowledge_workbench.claim_extraction"),
            status=status,
            attempt_count=1,
            next_attempt_at=WaitUntil(_now() + timedelta(hours=1)),
            last_error_kind="minute_limit",
        )

    if status in {
        WorkItemStatus.TERMINAL_FAILED,
        WorkItemStatus.CANCELLED,
    }:
        return WorkItem(
            work_item_id=item_id,
            work_kind=WorkKind("knowledge_workbench.claim_extraction"),
            status=status,
            attempt_count=1,
            last_error_kind="previous_terminal_state",
        )

    return WorkItem(
        work_item_id=item_id,
        work_kind=WorkKind("knowledge_workbench.claim_extraction"),
        status=status,
        attempt_count=1,
    )


def _command() -> CancelClaimExtractionStageCommand:
    return CancelClaimExtractionStageCommand(
        workflow_run_id="workflow-1",
        stage_run_id="stage-1",
        reason="cancelled_by_user",
        cancelled_by="manager-1",
        occurred_at=_now(),
    )


def test_cancels_ready_leased_deferred_and_user_action_required() -> None:
    reader = FakeStageWorkItemReader(
        work_items=(
            _work_item("ready-1", status=WorkItemStatus.READY),
            _work_item("leased-1", status=WorkItemStatus.LEASED),
            _work_item("deferred-1", status=WorkItemStatus.DEFERRED),
            _work_item("user-action-1", status=WorkItemStatus.USER_ACTION_REQUIRED),
        ),
    )
    unit_of_work = FakeStageCancellationUnitOfWork()

    result = CancelClaimExtractionStage(
        reader=reader,
        unit_of_work=unit_of_work,
    ).execute(_command())

    assert [item.status for item in result.cancelled_work_items] == [
        WorkItemStatus.CANCELLED,
        WorkItemStatus.CANCELLED,
        WorkItemStatus.CANCELLED,
        WorkItemStatus.CANCELLED,
    ]
    assert [item.work_item_id for item in unit_of_work.saved_work_items] == [
        "ready-1",
        "leased-1",
        "deferred-1",
        "user-action-1",
    ]
    assert all(
        item.last_error_kind == "cancelled_by_user"
        for item in result.cancelled_work_items
    )
    assert result.event.cancelled_count == 4
    assert reader.queries == [("workflow-1", "stage-1")]


def test_keeps_completed_and_terminal_items_untouched() -> None:
    completed = _work_item("completed-1", status=WorkItemStatus.COMPLETED)
    terminal = _work_item("terminal-1", status=WorkItemStatus.TERMINAL_FAILED)
    reader = FakeStageWorkItemReader(work_items=(completed, terminal))
    unit_of_work = FakeStageCancellationUnitOfWork()

    result = CancelClaimExtractionStage(
        reader=reader,
        unit_of_work=unit_of_work,
    ).execute(_command())

    assert result.cancelled_work_items == ()
    assert unit_of_work.saved_work_items == []
    assert result.skipped_completed_count == 1
    assert result.skipped_terminal_count == 1
    assert result.event.cancelled_count == 0


def test_does_not_delete_artifacts() -> None:
    artifact_repository = FakeArtifactRepository()
    reader = FakeStageWorkItemReader(
        work_items=(_work_item("ready-1", status=WorkItemStatus.READY),),
    )
    unit_of_work = FakeStageCancellationUnitOfWork()

    CancelClaimExtractionStage(reader=reader, unit_of_work=unit_of_work).execute(
        _command(),
    )

    assert artifact_repository.deleted_refs == []


def test_appends_stage_cancelled_event_and_commits_once() -> None:
    reader = FakeStageWorkItemReader(
        work_items=(_work_item("ready-1", status=WorkItemStatus.READY),),
    )
    unit_of_work = FakeStageCancellationUnitOfWork()

    result = CancelClaimExtractionStage(
        reader=reader,
        unit_of_work=unit_of_work,
    ).execute(_command())

    assert len(unit_of_work.events) == 1
    assert unit_of_work.events == [result.event]
    assert isinstance(unit_of_work.events[0], ClaimExtractionStageCancelled)
    assert result.event.workflow_run_id == "workflow-1"
    assert result.event.stage_run_id == "stage-1"
    assert result.event.reason == "cancelled_by_user"
    assert result.event.cancelled_by == "manager-1"
    assert unit_of_work.committed_count == 1
    assert unit_of_work.rolled_back_count == 0


def test_rolls_back_on_save_failure() -> None:
    reader = FakeStageWorkItemReader(
        work_items=(_work_item("ready-1", status=WorkItemStatus.READY),),
    )
    unit_of_work = FakeStageCancellationUnitOfWork(fail_on_save=True)

    with pytest.raises(RuntimeError, match="save failed"):
        CancelClaimExtractionStage(
            reader=reader,
            unit_of_work=unit_of_work,
        ).execute(_command())

    assert unit_of_work.committed_count == 0
    assert unit_of_work.rolled_back_count == 1


def test_cancel_command_rejects_empty_fields_and_naive_time() -> None:
    with pytest.raises(ValueError, match="workflow_run_id must be non-empty"):
        CancelClaimExtractionStageCommand(
            workflow_run_id="",
            stage_run_id="stage-1",
            reason="cancelled_by_user",
            cancelled_by="manager-1",
            occurred_at=_now(),
        )

    with pytest.raises(ValueError, match="occurred_at must be timezone-aware"):
        CancelClaimExtractionStageCommand(
            workflow_run_id="workflow-1",
            stage_run_id="stage-1",
            reason="cancelled_by_user",
            cancelled_by="manager-1",
            occurred_at=datetime(2026, 6, 8, 12, 0),
        )


def test_cancel_source_does_not_import_legacy_cancel_queue_db_or_artifact_deletion() -> (
    None
):
    source = Path(
        "src/contexts/knowledge_workbench/extraction/application/use_cases/"
        "cancel_claim_extraction_stage.py",
    ).read_text(encoding="utf-8")

    forbidden = (
        "src.application.workbench_commands.cancel_processing",
        "cancel_processing.py",
        "knowledge_workbench_section_batch_queue_items",
        "knowledge_workbench_parallel_section_batch_plans",
        "workbench_parallel_processing",
        "restore_checkpoint_service",
        "KnowledgeWorkbenchRepository",
        "FaqWorkbenchSectionWorkItemLeaseService",
        "SectionBatchQueueItem",
        "ProcessingNodeRun",
        "ProcessingNodeArtifact",
        "FaqWorkbench",
        "src.infrastructure.",
        "src.application.",
        "src.domain.project_plane.",
        "src.interfaces.",
        "asyncpg",
        "connection.execute",
        "fetchrow",
        "delete_artifact",
        "delete(",
        "ArtifactDeleted",
        "src.contexts.llm_runtime.infrastructure",
        "Groq",
        "groq",
        "type: ignore",
    )

    offenders = [marker for marker in forbidden if marker in source]
    assert not offenders
