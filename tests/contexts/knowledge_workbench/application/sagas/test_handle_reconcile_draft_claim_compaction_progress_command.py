from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.knowledge_workbench.application.sagas.handle_reconcile_draft_claim_compaction_progress_command import (
    HandleReconcileDraftClaimCompactionProgressCommand,
    HandleReconcileDraftClaimCompactionProgressCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_progress import (
    DraftClaimCompactionProgressSummary,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.entities.workflow_event_cursor import (
    WorkflowEventCursor,
)
from src.contexts.workflow_runtime.domain.entities.workflow_progress_snapshot import (
    WorkflowProgressSnapshot,
)
from src.contexts.workflow_runtime.domain.entities.workflow_resource_usage_snapshot import (
    WorkflowResourceUsageSnapshot,
)
from src.contexts.workflow_runtime.domain.entities.workflow_timeline_entry import (
    WorkflowTimelineEntry,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_consumer_ref import (
    WorkflowConsumerRef,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)


def _now() -> datetime:
    return datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "workflow-1"


def _command(
    *,
    command_type: KnowledgeExtractionCanonicalCommandType = (
        KnowledgeExtractionCanonicalCommandType.RECONCILE_DRAFT_CLAIM_COMPACTION_PROGRESS
    ),
    status: WorkflowCommandStatus = WorkflowCommandStatus.PENDING,
) -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{command_type.value}"),
        command_type=command_type.value,
        workflow_run_id=_workflow_run_id(),
        idempotency_key=WorkflowIdempotencyKey(f"{command_type.value}:workflow-1"),
        payload={"workflow_run_id": _workflow_run_id()},
        status=status,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


@dataclass(slots=True)
class FakeReductionStateRepository:
    summary: DraftClaimCompactionProgressSummary

    async def summarize_compaction_progress(
        self,
        *,
        workflow_run_id: str,
    ) -> DraftClaimCompactionProgressSummary:
        assert workflow_run_id == _workflow_run_id()
        return self.summary


@dataclass(slots=True)
class FakeCommandLog:
    pending_commands: list[WorkflowCommand] = field(default_factory=list)
    completed: list[WorkflowCommandId] = field(default_factory=list)

    async def append_pending_command(self, command: WorkflowCommand) -> WorkflowCommand:
        self.pending_commands.append(command)
        return command

    async def mark_command_completed(
        self,
        *,
        command_id: WorkflowCommandId,
        completed_at: datetime,
    ) -> WorkflowCommand:
        del completed_at
        self.completed.append(command_id)
        return _command()

    async def list_pending_commands(
        self,
        *,
        workflow_run_id: str,
        limit: int,
    ) -> tuple[WorkflowCommand, ...]:
        del workflow_run_id, limit
        return ()


@dataclass(slots=True)
class FakeOutbox:
    events: list[WorkflowEvent] = field(default_factory=list)

    async def append_event(self, event: WorkflowEvent) -> WorkflowEvent:
        self.events.append(event)
        return event

    async def list_events_after(
        self,
        *,
        consumer_ref: WorkflowConsumerRef,
        after_sequence_number: int,
        limit: int,
    ) -> tuple[WorkflowEvent, ...]:
        del consumer_ref, after_sequence_number, limit
        return tuple(self.events)


@dataclass(slots=True)
class FakeEventCursors:
    async def get_cursor(
        self,
        consumer_ref: WorkflowConsumerRef,
    ) -> WorkflowEventCursor | None:
        del consumer_ref
        return None

    async def save_cursor(self, cursor: WorkflowEventCursor) -> WorkflowEventCursor:
        return cursor


@dataclass(slots=True)
class FakeProgressSnapshots:
    snapshot: WorkflowProgressSnapshot | None = None

    async def get_snapshot(
        self,
        workflow_run_id: str,
    ) -> WorkflowProgressSnapshot | None:
        del workflow_run_id
        return self.snapshot

    async def save_snapshot(
        self,
        snapshot: WorkflowProgressSnapshot,
    ) -> WorkflowProgressSnapshot:
        self.snapshot = snapshot
        return snapshot


@dataclass(slots=True)
class FakeTimeline:
    entries: list[WorkflowTimelineEntry] = field(default_factory=list)

    async def append_entry(self, entry: WorkflowTimelineEntry) -> WorkflowTimelineEntry:
        self.entries.append(entry)
        return entry

    async def list_recent_entries(
        self,
        *,
        workflow_run_id: str,
        limit: int,
    ) -> tuple[WorkflowTimelineEntry, ...]:
        del workflow_run_id, limit
        return tuple(self.entries)


@dataclass(slots=True)
class FakeResourceUsage:
    usage: WorkflowResourceUsageSnapshot | None = None

    async def get_usage(
        self,
        workflow_run_id: str,
    ) -> WorkflowResourceUsageSnapshot | None:
        del workflow_run_id
        return self.usage

    async def save_usage(
        self,
        usage: WorkflowResourceUsageSnapshot,
    ) -> WorkflowResourceUsageSnapshot:
        self.usage = usage
        return usage


@dataclass(slots=True)
class FakeWorkflowUnitOfWork:
    command_log: FakeCommandLog = field(default_factory=FakeCommandLog)
    outbox: FakeOutbox = field(default_factory=FakeOutbox)
    event_cursors: FakeEventCursors = field(default_factory=FakeEventCursors)
    progress_snapshots: FakeProgressSnapshots = field(
        default_factory=FakeProgressSnapshots
    )
    timeline: FakeTimeline = field(default_factory=FakeTimeline)
    resource_usage: FakeResourceUsage = field(default_factory=FakeResourceUsage)

    async def commit(self) -> None:
        raise AssertionError("handler must not commit")

    async def rollback(self) -> None:
        raise AssertionError("handler must not rollback")


@pytest.mark.asyncio
async def test_active_groups_reconciles_progress_and_completes_command() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    repository = FakeReductionStateRepository(_summary(active_group_count=2))

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
    )

    assert result.decision == "ACTIVE"
    assert [event.event_type for event in workflow_uow.outbox.events] == [
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_PROGRESS_RECONCILED.value,
    ]
    assert workflow_uow.progress_snapshots.snapshot is not None
    assert len(workflow_uow.timeline.entries) == 1
    assert workflow_uow.command_log.completed == [_command().command_id]
    assert workflow_uow.command_log.pending_commands == []


@pytest.mark.asyncio
async def test_active_due_work_items_appends_prepare_command() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    repository = FakeReductionStateRepository(
        _summary(
            active_group_count=2,
            active_work_item_count=1,
            ready_work_item_count=1,
            due_waiting_work_item_count=1,
        )
    )

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
    )

    assert result.decision == "PREPARE_NEXT_BATCH_NOW"
    assert result.appended_next_command_count == 1
    assert len(workflow_uow.command_log.pending_commands) == 1
    next_command = workflow_uow.command_log.pending_commands[0]
    assert (
        next_command.command_type
        == KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH.value
    )
    assert next_command.payload["scheduled_work_item_count"] == 1
    assert next_command.run_after == _now()
    assert next_command.payload["active_model_ref"] == "openai/gpt-oss-120b"
    assert next_command.payload["caused_by_command_id"] == _command().command_id.value
    assert ":reconcile:now:" in next_command.idempotency_key.value
    dispatch_preparation = next_command.payload["llm_dispatch_preparation"]
    assert isinstance(dispatch_preparation, dict)
    assert dispatch_preparation["active_model_ref"] == "openai/gpt-oss-120b"
    assert dispatch_preparation["requested_items"] == 1
    assert "account_capacities" not in dispatch_preparation


@pytest.mark.asyncio
async def test_future_due_work_items_append_delayed_prepare_command() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    next_due_at = _now() + timedelta(seconds=45)
    repository = FakeReductionStateRepository(
        _summary(
            active_group_count=2,
            active_work_item_count=3,
            deferred_work_item_count=2,
            retryable_failed_work_item_count=1,
            due_waiting_work_item_count=0,
            next_due_at=next_due_at,
        )
    )

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
    )

    assert result.decision == "PREPARE_NEXT_BATCH_LATER"
    assert result.appended_next_command_count == 1
    assert len(workflow_uow.command_log.pending_commands) == 1
    next_command = workflow_uow.command_log.pending_commands[0]
    assert (
        next_command.command_type
        == KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH.value
    )
    assert next_command.run_after == next_due_at
    assert next_command.payload["scheduled_work_item_count"] == 3
    assert ":reconcile:later:" in next_command.idempotency_key.value
    dispatch_preparation = next_command.payload["llm_dispatch_preparation"]
    assert isinstance(dispatch_preparation, dict)
    assert dispatch_preparation["requested_items"] == 3
    assert "account_capacities" not in dispatch_preparation


@pytest.mark.asyncio
async def test_all_groups_done_appends_done_event_and_curation_command() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    repository = FakeReductionStateRepository(
        _summary(group_count=2, done_group_count=2, active_group_count=0)
    )

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
    )

    assert result.decision == "ALL_GROUPS_COMPACTED"
    assert [event.event_type for event in workflow_uow.outbox.events] == [
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_PROGRESS_RECONCILED.value,
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_ALL_GROUPS_COMPACTED.value,
    ]
    assert len(workflow_uow.command_log.pending_commands) == 1
    assert (
        workflow_uow.command_log.pending_commands[0].command_type
        == KnowledgeExtractionCanonicalCommandType.OPEN_DRAFT_CLAIM_CURATION_WORKSPACE.value
    )
    assert workflow_uow.command_log.completed == [_command().command_id]


@pytest.mark.asyncio
async def test_waiting_user_choice_blocks_without_preview_command() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    repository = FakeReductionStateRepository(
        _summary(
            group_count=2,
            waiting_user_model_choice_group_count=1,
            active_group_count=1,
        )
    )

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
    )

    assert result.decision == "WAITING_USER_MODEL_CHOICE"
    assert [event.event_type for event in workflow_uow.outbox.events] == [
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_PROGRESS_RECONCILED.value,
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_WAITING_USER_MODEL_CHOICE.value,
    ]
    assert workflow_uow.command_log.pending_commands == []
    assert workflow_uow.progress_snapshots.snapshot is not None
    assert workflow_uow.progress_snapshots.snapshot.blocked_work_items == 1
    assert workflow_uow.progress_snapshots.snapshot.workflow_status == "BLOCKED"


@pytest.mark.asyncio
async def test_rejects_wrong_command_type() -> None:
    with pytest.raises(ValueError, match="ReconcileDraftClaimCompactionProgress"):
        await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
            HandleReconcileDraftClaimCompactionProgressCommand(
                workflow_command=_command(
                    command_type=KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS
                )
            ),
            workflow_unit_of_work=FakeWorkflowUnitOfWork(),
            compaction_reduction_state_repository=FakeReductionStateRepository(
                _summary()
            ),
        )


@pytest.mark.asyncio
async def test_rejects_non_pending_command() -> None:
    with pytest.raises(ValueError, match="PENDING"):
        await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
            HandleReconcileDraftClaimCompactionProgressCommand(
                workflow_command=_command(status=WorkflowCommandStatus.COMPLETED)
            ),
            workflow_unit_of_work=FakeWorkflowUnitOfWork(),
            compaction_reduction_state_repository=FakeReductionStateRepository(
                _summary()
            ),
        )


def _summary(
    *,
    group_count: int = 2,
    done_group_count: int = 0,
    waiting_user_model_choice_group_count: int = 0,
    active_group_count: int = 2,
    active_work_item_count: int = 0,
    ready_work_item_count: int = 0,
    leased_work_item_count: int = 0,
    deferred_work_item_count: int = 0,
    retryable_failed_work_item_count: int = 0,
    terminal_failed_work_item_count: int = 0,
    due_waiting_work_item_count: int = 0,
    next_due_at: datetime | None = None,
) -> DraftClaimCompactionProgressSummary:
    return DraftClaimCompactionProgressSummary(
        workflow_run_id=_workflow_run_id(),
        group_count=group_count,
        done_group_count=done_group_count,
        waiting_user_model_choice_group_count=waiting_user_model_choice_group_count,
        active_group_count=active_group_count,
        active_node_count=4,
        pending_comparison_count=1,
        active_work_item_count=active_work_item_count,
        completed_work_item_count=0,
        failed_work_item_count=(
            retryable_failed_work_item_count + terminal_failed_work_item_count
        ),
        ready_work_item_count=ready_work_item_count,
        leased_work_item_count=leased_work_item_count,
        deferred_work_item_count=deferred_work_item_count,
        retryable_failed_work_item_count=retryable_failed_work_item_count,
        terminal_failed_work_item_count=terminal_failed_work_item_count,
        due_waiting_work_item_count=due_waiting_work_item_count,
        next_due_at=next_due_at,
    )
