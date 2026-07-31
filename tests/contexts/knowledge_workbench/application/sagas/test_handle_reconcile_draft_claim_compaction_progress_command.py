from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.knowledge_workbench.application.sagas.handle_reconcile_draft_claim_compaction_progress_command import (
    HandleReconcileDraftClaimCompactionProgressCommand,
    HandleReconcileDraftClaimCompactionProgressCommandHandler,
)
from src.contexts.execution_runtime.application.ports.work_item_progress_read_repository_port import (
    WorkItemProgressSummary,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
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


def _pending_command(
    command_type: KnowledgeExtractionCanonicalCommandType,
    *,
    command_id: str | None = None,
    run_after: datetime | None = None,
) -> WorkflowCommand:
    command_id_value = (
        f"workflow-command:{command_type.value}:pending"
        if command_id is None
        else command_id
    )
    return WorkflowCommand(
        command_id=WorkflowCommandId(command_id_value),
        command_type=command_type.value,
        workflow_run_id=_workflow_run_id(),
        idempotency_key=WorkflowIdempotencyKey(f"{command_id_value}:idempotency"),
        payload={"workflow_run_id": _workflow_run_id()},
        status=WorkflowCommandStatus.PENDING,
        run_after=_now() if run_after is None else run_after,
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
class FakeWorkItemProgressReadRepository:
    summary: WorkItemProgressSummary
    calls: list[tuple[str, WorkKind, datetime]] = field(default_factory=list)

    async def summarize_by_work_kind_and_workflow(
        self,
        *,
        workflow_run_id: str,
        work_kind: WorkKind,
        now: datetime,
    ) -> WorkItemProgressSummary:
        self.calls.append((workflow_run_id, work_kind, now))
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

    async def has_pending_commands(
        self,
        *,
        workflow_run_id: str,
        command_types: tuple[str, ...],
        excluding_command_id: WorkflowCommandId | None = None,
    ) -> bool:
        return any(
            command.workflow_run_id == workflow_run_id
            and command.status is WorkflowCommandStatus.PENDING
            and command.command_id not in self.completed
            and command.command_type in command_types
            and command.command_id != excluding_command_id
            for command in self.pending_commands
        )


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
async def test_leased_work_reconciles_active_without_prepare() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    repository = FakeReductionStateRepository(_summary(active_group_count=2))
    execution_repository = FakeWorkItemProgressReadRepository(
        _work_summary(leased_count=1)
    )

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        work_item_progress_read_repository=execution_repository,
    )

    assert result.decision == "ACTIVE"
    assert execution_repository.calls == [
        (
            _workflow_run_id(),
            WorkKind("knowledge_workbench.draft_claim_compaction"),
            _now(),
        )
    ]
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
        )
    )
    execution_repository = FakeWorkItemProgressReadRepository(_work_summary(ready_count=1))

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        work_item_progress_read_repository=execution_repository,
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
async def test_future_retryable_work_items_append_delayed_prepare_command() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    next_due_at = _now() + timedelta(seconds=45)
    repository = FakeReductionStateRepository(
        _summary(
            active_group_count=2,
        )
    )
    execution_repository = FakeWorkItemProgressReadRepository(
        _work_summary(
            retryable_failed_count=3,
            due_retryable_failed_count=0,
            next_due_at=next_due_at,
        )
    )

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        work_item_progress_read_repository=execution_repository,
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
async def test_future_deferred_work_items_are_counted_for_delayed_prepare() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    next_due_at = _now() + timedelta(seconds=45)
    repository = FakeReductionStateRepository(_summary(active_group_count=2))
    execution_repository = FakeWorkItemProgressReadRepository(
        _work_summary(
            deferred_count=4,
            due_deferred_count=0,
            next_due_at=next_due_at,
        )
    )

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        work_item_progress_read_repository=execution_repository,
    )

    assert result.decision == "PREPARE_NEXT_BATCH_LATER"
    assert workflow_uow.command_log.pending_commands[0].payload[
        "scheduled_work_item_count"
    ] == 4


@pytest.mark.asyncio
async def test_future_retryable_and_deferred_counts_are_combined() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    next_due_at = _now() + timedelta(seconds=45)
    repository = FakeReductionStateRepository(_summary(active_group_count=2))
    execution_repository = FakeWorkItemProgressReadRepository(
        _work_summary(
            deferred_count=3,
            due_deferred_count=0,
            retryable_failed_count=2,
            due_retryable_failed_count=0,
            next_due_at=next_due_at,
        )
    )

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        work_item_progress_read_repository=execution_repository,
    )

    assert result.decision == "PREPARE_NEXT_BATCH_LATER"
    assert workflow_uow.command_log.pending_commands[0].payload[
        "scheduled_work_item_count"
    ] == 5


@pytest.mark.asyncio
async def test_future_decision_requires_next_due_at() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    repository = FakeReductionStateRepository(_summary(active_group_count=2))
    execution_repository = FakeWorkItemProgressReadRepository(
        _work_summary(retryable_failed_count=1, due_retryable_failed_count=0)
    )

    with pytest.raises(ValueError, match="next_due_at"):
        await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
            HandleReconcileDraftClaimCompactionProgressCommand(
                workflow_command=_command()
            ),
            workflow_unit_of_work=workflow_uow,
            compaction_reduction_state_repository=repository,
            work_item_progress_read_repository=execution_repository,
        )


@pytest.mark.asyncio
async def test_all_groups_done_appends_done_event_and_curation_command() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    repository = FakeReductionStateRepository(
        _summary(group_count=2, done_group_count=2, active_group_count=0)
    )
    execution_repository = FakeWorkItemProgressReadRepository(
        _work_summary(completed_count=2)
    )

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        work_item_progress_read_repository=execution_repository,
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
async def test_all_groups_done_with_terminal_failure_blocks_without_curation() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    repository = FakeReductionStateRepository(
        _summary(group_count=2, done_group_count=2, active_group_count=0)
    )
    execution_repository = FakeWorkItemProgressReadRepository(
        _work_summary(completed_count=1, terminal_failed_count=1)
    )

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        work_item_progress_read_repository=execution_repository,
    )

    assert result.decision == "COMPACTION_PROGRESS_BLOCKED"
    assert workflow_uow.outbox.events[-1].payload["reason"] == (
        "terminal_execution_failure"
    )
    assert workflow_uow.command_log.pending_commands == []


@pytest.mark.asyncio
async def test_all_groups_done_with_due_work_prepares_without_curation() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    repository = FakeReductionStateRepository(
        _summary(group_count=2, done_group_count=2, active_group_count=0)
    )
    execution_repository = FakeWorkItemProgressReadRepository(
        _work_summary(completed_count=1, retryable_failed_count=1, due_retryable_failed_count=1)
    )

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        work_item_progress_read_repository=execution_repository,
    )

    assert result.decision == "PREPARE_NEXT_BATCH_NOW"
    assert workflow_uow.command_log.pending_commands[0].command_type == (
        KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH.value
    )


@pytest.mark.asyncio
async def test_due_work_with_pending_compaction_continuation_stays_active() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    workflow_uow.command_log.pending_commands.append(
        _command(
            command_type=(
                KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH
            )
        )
    )
    repository = FakeReductionStateRepository(
        _summary(group_count=2, done_group_count=1, active_group_count=1)
    )
    execution_repository = FakeWorkItemProgressReadRepository(
        _work_summary(
            completed_count=1,
            retryable_failed_count=1,
            due_retryable_failed_count=1,
        )
    )

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        work_item_progress_read_repository=execution_repository,
    )

    assert result.decision == "ACTIVE"
    assert len(workflow_uow.command_log.pending_commands) == 1


@pytest.mark.asyncio
async def test_all_groups_done_ignores_stale_pending_prepare_wakeup() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    workflow_uow.command_log.pending_commands.append(
        _pending_command(
            KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH,
            run_after=_now() + timedelta(minutes=1),
        )
    )
    repository = FakeReductionStateRepository(
        _summary(group_count=2, done_group_count=2, active_group_count=0)
    )
    execution_repository = FakeWorkItemProgressReadRepository(
        _work_summary(completed_count=2)
    )

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        work_item_progress_read_repository=execution_repository,
    )

    assert result.decision == "ALL_GROUPS_COMPACTED"
    assert workflow_uow.command_log.pending_commands[-1].command_type == (
        KnowledgeExtractionCanonicalCommandType.OPEN_DRAFT_CLAIM_CURATION_WORKSPACE.value
    )


@pytest.mark.asyncio
async def test_all_groups_done_with_unclean_terminal_coverage_blocks() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    repository = FakeReductionStateRepository(
        _summary(group_count=2, done_group_count=2, active_group_count=0)
    )
    execution_repository = FakeWorkItemProgressReadRepository(
        _unchecked_work_summary(completed_count=1, total_count=2)
    )

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        work_item_progress_read_repository=execution_repository,
    )

    assert result.decision == "COMPACTION_PROGRESS_BLOCKED"
    assert workflow_uow.outbox.events[-1].payload["reason"] == (
        "unclean_terminal_coverage"
    )
    assert workflow_uow.command_log.pending_commands == []


@pytest.mark.asyncio
async def test_all_groups_done_with_leased_work_stays_active_without_curation() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    repository = FakeReductionStateRepository(
        _summary(group_count=2, done_group_count=2, active_group_count=0)
    )
    execution_repository = FakeWorkItemProgressReadRepository(
        _work_summary(completed_count=1, leased_count=1)
    )

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        work_item_progress_read_repository=execution_repository,
    )

    assert result.decision == "ACTIVE"
    assert workflow_uow.command_log.pending_commands == []


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
    execution_repository = FakeWorkItemProgressReadRepository(_work_summary())

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        work_item_progress_read_repository=execution_repository,
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
            work_item_progress_read_repository=FakeWorkItemProgressReadRepository(
                _work_summary()
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
            work_item_progress_read_repository=FakeWorkItemProgressReadRepository(
                _work_summary()
            ),
        )


@pytest.mark.asyncio
async def test_terminal_failed_work_blocks_without_curation_command() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    repository = FakeReductionStateRepository(
        _summary(group_count=2, done_group_count=1, active_group_count=1)
    )
    execution_repository = FakeWorkItemProgressReadRepository(
        _work_summary(completed_count=1, terminal_failed_count=1)
    )

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        work_item_progress_read_repository=execution_repository,
    )

    assert result.decision == "COMPACTION_PROGRESS_BLOCKED"
    assert [event.event_type for event in workflow_uow.outbox.events] == [
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_PROGRESS_RECONCILED.value,
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_PROGRESS_BLOCKED.value,
    ]
    assert workflow_uow.outbox.events[-1].payload["reason"] == (
        "terminal_execution_failure"
    )
    assert workflow_uow.command_log.pending_commands == []
    assert workflow_uow.progress_snapshots.snapshot is not None
    assert workflow_uow.progress_snapshots.snapshot.workflow_status == "BLOCKED"


@pytest.mark.asyncio
async def test_incomplete_group_without_queue_continuation_blocks() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    repository = FakeReductionStateRepository(
        _summary(group_count=2, done_group_count=1, active_group_count=1)
    )
    execution_repository = FakeWorkItemProgressReadRepository(_work_summary())

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        work_item_progress_read_repository=execution_repository,
    )

    assert result.decision == "COMPACTION_PROGRESS_BLOCKED"
    assert workflow_uow.outbox.events[-1].payload["reason"] == (
        "incomplete_groups_without_continuation"
    )
    assert workflow_uow.command_log.pending_commands == []


@pytest.mark.parametrize(
    "continuation_type",
    [
        KnowledgeExtractionCanonicalCommandType.APPLY_DRAFT_CLAIM_COMPACTION_RESULT,
        KnowledgeExtractionCanonicalCommandType.EXECUTE_DRAFT_CLAIM_COMPACTION,
        KnowledgeExtractionCanonicalCommandType.RECONCILE_DRAFT_CLAIM_COMPACTION_PROGRESS,
    ],
)
@pytest.mark.asyncio
async def test_incomplete_zero_queue_with_pending_continuation_stays_active(
    continuation_type: KnowledgeExtractionCanonicalCommandType,
) -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    workflow_uow.command_log.pending_commands.append(
        _pending_command(continuation_type, command_id=f"pending:{continuation_type.value}")
    )
    repository = FakeReductionStateRepository(_summary(active_group_count=1))
    execution_repository = FakeWorkItemProgressReadRepository(_work_summary())

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        work_item_progress_read_repository=execution_repository,
    )

    assert result.decision == "ACTIVE"
    assert all(
        event.event_type
        != KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_PROGRESS_BLOCKED.value
        for event in workflow_uow.outbox.events
    )


@pytest.mark.asyncio
async def test_incomplete_zero_queue_with_future_pending_prepare_stays_active() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    workflow_uow.command_log.pending_commands.append(
        _pending_command(
            KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH,
            run_after=_now() + timedelta(minutes=5),
        )
    )
    repository = FakeReductionStateRepository(_summary(active_group_count=1))
    execution_repository = FakeWorkItemProgressReadRepository(_work_summary())

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        work_item_progress_read_repository=execution_repository,
    )

    assert result.decision == "ACTIVE"
    assert all(
        event.event_type
        != KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_PROGRESS_BLOCKED.value
        for event in workflow_uow.outbox.events
    )


@pytest.mark.asyncio
async def test_incomplete_zero_queue_with_only_current_reconcile_blocks() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    current_command = _command()
    workflow_uow.command_log.pending_commands.append(current_command)
    repository = FakeReductionStateRepository(_summary(active_group_count=1))
    execution_repository = FakeWorkItemProgressReadRepository(_work_summary())

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(
            workflow_command=current_command
        ),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        work_item_progress_read_repository=execution_repository,
    )

    assert result.decision == "COMPACTION_PROGRESS_BLOCKED"


@pytest.mark.asyncio
async def test_terminal_failure_blocks_despite_pending_apply() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    workflow_uow.command_log.pending_commands.append(
        _pending_command(
            KnowledgeExtractionCanonicalCommandType.APPLY_DRAFT_CLAIM_COMPACTION_RESULT
        )
    )
    repository = FakeReductionStateRepository(_summary(active_group_count=1))
    execution_repository = FakeWorkItemProgressReadRepository(
        _work_summary(terminal_failed_count=1)
    )

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        work_item_progress_read_repository=execution_repository,
    )

    assert result.decision == "COMPACTION_PROGRESS_BLOCKED"
    assert workflow_uow.outbox.events[-1].payload["reason"] == (
        "terminal_execution_failure"
    )


@pytest.mark.asyncio
async def test_all_groups_done_unclean_coverage_with_pending_open_stays_active() -> None:
    workflow_uow = FakeWorkflowUnitOfWork()
    workflow_uow.command_log.pending_commands.append(
        _pending_command(
            KnowledgeExtractionCanonicalCommandType.OPEN_DRAFT_CLAIM_CURATION_WORKSPACE
        )
    )
    repository = FakeReductionStateRepository(
        _summary(group_count=2, done_group_count=2, active_group_count=0)
    )
    execution_repository = FakeWorkItemProgressReadRepository(
        _unchecked_work_summary(completed_count=1, total_count=2)
    )

    result = await HandleReconcileDraftClaimCompactionProgressCommandHandler().execute(
        HandleReconcileDraftClaimCompactionProgressCommand(workflow_command=_command()),
        workflow_unit_of_work=workflow_uow,
        compaction_reduction_state_repository=repository,
        work_item_progress_read_repository=execution_repository,
    )

    assert result.decision == "ACTIVE"
    assert len(workflow_uow.command_log.pending_commands) == 1
    assert workflow_uow.command_log.pending_commands[0].command_type == (
        KnowledgeExtractionCanonicalCommandType.OPEN_DRAFT_CLAIM_CURATION_WORKSPACE.value
    )
    assert all(
        event.event_type
        != KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_PROGRESS_BLOCKED.value
        for event in workflow_uow.outbox.events
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


def _work_summary(
    *,
    ready_count: int = 0,
    leased_count: int = 0,
    deferred_count: int = 0,
    retryable_failed_count: int = 0,
    completed_count: int = 0,
    terminal_failed_count: int = 0,
    cancelled_count: int = 0,
    split_superseded_count: int = 0,
    user_action_required_count: int = 0,
    next_due_at: datetime | None = None,
    due_deferred_count: int = 0,
    due_retryable_failed_count: int = 0,
) -> WorkItemProgressSummary:
    return WorkItemProgressSummary(
        ready_count=ready_count,
        leased_count=leased_count,
        deferred_count=deferred_count,
        retryable_failed_count=retryable_failed_count,
        completed_count=completed_count,
        terminal_failed_count=terminal_failed_count,
        cancelled_count=cancelled_count,
        split_superseded_count=split_superseded_count,
        user_action_required_count=user_action_required_count,
        total_count=(
            ready_count
            + leased_count
            + deferred_count
            + retryable_failed_count
            + completed_count
            + terminal_failed_count
            + cancelled_count
            + split_superseded_count
            + user_action_required_count
        ),
        next_due_at=next_due_at,
        due_deferred_count=due_deferred_count,
        due_retryable_failed_count=due_retryable_failed_count,
    )


def _unchecked_work_summary(
    *,
    completed_count: int,
    total_count: int,
) -> WorkItemProgressSummary:
    summary = object.__new__(WorkItemProgressSummary)
    for field_name, value in {
        "ready_count": 0,
        "leased_count": 0,
        "deferred_count": 0,
        "retryable_failed_count": 0,
        "completed_count": completed_count,
        "terminal_failed_count": 0,
        "cancelled_count": 0,
        "split_superseded_count": 0,
        "user_action_required_count": 0,
        "total_count": total_count,
        "next_due_at": None,
        "due_deferred_count": 0,
        "due_retryable_failed_count": 0,
    }.items():
        object.__setattr__(summary, field_name, value)
    return summary
