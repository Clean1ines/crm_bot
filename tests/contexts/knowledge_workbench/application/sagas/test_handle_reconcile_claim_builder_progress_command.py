from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest

from src.contexts.execution_runtime.application.ports.work_item_progress_read_repository_port import (
    WorkItemProgressSummary,
)
from src.contexts.knowledge_workbench.extraction.application.ports.claim_builder_retry_action_read_repository_port import (
    WorkItemRetryActionSummary,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.application.sagas.handle_reconcile_claim_builder_progress_command import (
    ClaimBuilderProgressReconcileDecision,
    HandleReconcileClaimBuilderProgressCommand,
    HandleReconcileClaimBuilderProgressCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.application.sagas.plan_claim_builder_section_work import (
    CLAIM_BUILDER_SECTION_WORK_KIND,
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
    return datetime(2026, 6, 12, 12, 0, tzinfo=UTC)


def _workflow_run_id() -> str:
    return "knowledge-extraction:source-document:project-1:abc"


def _dispatch_preparation() -> dict[str, object]:
    return {
        "profile": {
            "profile_id": "faq_claim_observations",
            "estimated_prompt_tokens": 3000,
            "estimated_completion_tokens": 500,
            "estimated_requests": 1,
        },
        "account_capacities": (
            {
                "provider": "groq",
                "account_ref": "groq_org_primary",
                "model_ref": "qwen/qwen3-32b",
                "remaining_minute_requests": 1,
                "remaining_minute_tokens": 7000,
                "remaining_daily_requests": 100,
                "remaining_daily_tokens": 50000,
            },
        ),
        "active_model_ref": "qwen/qwen3-32b",
        "requested_items": 1,
        "worker_ref": "worker-1",
        "lease_token_prefix": "lease-prefix",
        "lease_ttl_seconds": 300,
    }


def _workflow_command(
    *,
    command_type: str = KnowledgeExtractionCanonicalCommandType.RECONCILE_CLAIM_BUILDER_PROGRESS.value,
    status: WorkflowCommandStatus = WorkflowCommandStatus.PENDING,
    workflow_run_id: str = _workflow_run_id(),
    payload_workflow_run_id: str | None = None,
    reconcile_ref: str = "work-1-attempt-1",
) -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId(
            f"workflow-command:reconcile-claim-builder-progress:{workflow_run_id}:{reconcile_ref}"
        ),
        command_type=command_type,
        workflow_run_id=workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(
            f"reconcile-claim-builder-progress:{workflow_run_id}:{reconcile_ref}"
        ),
        payload={
            "workflow_run_id": payload_workflow_run_id or workflow_run_id,
            "dispatch_attempt_id": "work-1:attempt:1",
            "work_item_id": "work-1",
            "work_kind": CLAIM_BUILDER_SECTION_WORK_KIND.value,
            "llm_dispatch_preparation": _dispatch_preparation(),
        },
        status=status,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


def _summary(
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
    total_count = (
        ready_count
        + leased_count
        + deferred_count
        + retryable_failed_count
        + completed_count
        + terminal_failed_count
        + cancelled_count
        + split_superseded_count
        + user_action_required_count
    )
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
        total_count=total_count,
        next_due_at=next_due_at,
        due_deferred_count=due_deferred_count,
        due_retryable_failed_count=due_retryable_failed_count,
    )


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


def _retry_action_summary(
    *,
    retry_same_model_count: int = 0,
    retry_empty_claims_check_model_count: int = 0,
    retry_fallback_model_count: int = 0,
    retry_larger_output_model_count: int = 0,
    retry_larger_input_model_count: int = 0,
    split_required_count: int = 0,
    defer_until_capacity_reset_count: int = 0,
    pause_for_daily_limit_reset_count: int = 0,
    request_user_low_quality_continue_or_wait_count: int = 0,
    next_run_after: datetime | None = None,
) -> WorkItemRetryActionSummary:
    return WorkItemRetryActionSummary(
        workflow_run_id=_workflow_run_id(),
        work_kind=CLAIM_BUILDER_SECTION_WORK_KIND,
        retry_same_model_count=retry_same_model_count,
        retry_empty_claims_check_model_count=retry_empty_claims_check_model_count,
        retry_fallback_model_count=retry_fallback_model_count,
        retry_larger_output_model_count=retry_larger_output_model_count,
        retry_larger_input_model_count=retry_larger_input_model_count,
        split_required_count=split_required_count,
        defer_until_capacity_reset_count=defer_until_capacity_reset_count,
        pause_for_daily_limit_reset_count=pause_for_daily_limit_reset_count,
        request_user_low_quality_continue_or_wait_count=(
            request_user_low_quality_continue_or_wait_count
        ),
        next_run_after=next_run_after,
    )


@dataclass(slots=True)
class FakeClaimBuilderRetryActionReadRepository:
    summary: WorkItemRetryActionSummary = field(default_factory=_retry_action_summary)
    calls: list[tuple[str, WorkKind, datetime]] = field(default_factory=list)

    async def summarize_retry_actions(
        self,
        *,
        workflow_run_id: str,
        work_kind: WorkKind,
        now: datetime,
    ) -> WorkItemRetryActionSummary:
        self.calls.append((workflow_run_id, work_kind, now))
        return self.summary


@dataclass(slots=True)
class FakeCommandLogRepository:
    pending_commands: list[WorkflowCommand] = field(default_factory=list)
    completed_command_ids: list[WorkflowCommandId] = field(default_factory=list)

    async def append_pending_command(
        self,
        command: WorkflowCommand,
    ) -> WorkflowCommand:
        self.pending_commands.append(command)
        return command

    async def mark_command_completed(
        self,
        *,
        command_id: WorkflowCommandId,
        completed_at: datetime,
    ) -> WorkflowCommand:
        del completed_at
        self.completed_command_ids.append(command_id)
        return _workflow_command(status=WorkflowCommandStatus.COMPLETED)


@dataclass(slots=True)
class FakeOutboxRepository:
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
class FakeEventCursorRepository:
    async def get_cursor(
        self,
        consumer_ref: WorkflowConsumerRef,
    ) -> WorkflowEventCursor | None:
        del consumer_ref
        return None

    async def save_cursor(
        self,
        cursor: WorkflowEventCursor,
    ) -> WorkflowEventCursor:
        return cursor


@dataclass(slots=True)
class FakeProgressSnapshotRepository:
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
class FakeTimelineRepository:
    entries: list[WorkflowTimelineEntry] = field(default_factory=list)

    async def append_entry(
        self,
        entry: WorkflowTimelineEntry,
    ) -> WorkflowTimelineEntry:
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
class FakeResourceUsageRepository:
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
class FakeWorkflowRuntimeUnitOfWork:
    command_log: FakeCommandLogRepository = field(
        default_factory=FakeCommandLogRepository,
    )
    outbox: FakeOutboxRepository = field(default_factory=FakeOutboxRepository)
    event_cursors: FakeEventCursorRepository = field(
        default_factory=FakeEventCursorRepository,
    )
    progress_snapshots: FakeProgressSnapshotRepository = field(
        default_factory=FakeProgressSnapshotRepository,
    )
    timeline: FakeTimelineRepository = field(default_factory=FakeTimelineRepository)
    resource_usage: FakeResourceUsageRepository = field(
        default_factory=FakeResourceUsageRepository,
    )

    async def commit(self) -> None:
        raise AssertionError("handler must not own transaction commit")

    async def rollback(self) -> None:
        raise AssertionError("handler must not own transaction rollback")


async def _execute(
    *,
    workflow_command: WorkflowCommand | None = None,
    summary: WorkItemProgressSummary | None = None,
    retry_action_summary: WorkItemRetryActionSummary | None = None,
) -> tuple[
    object,
    FakeWorkItemProgressReadRepository,
    FakeClaimBuilderRetryActionReadRepository,
    FakeWorkflowRuntimeUnitOfWork,
]:
    progress_repository = FakeWorkItemProgressReadRepository(
        summary=summary or _summary(ready_count=1),
    )
    retry_action_repository = FakeClaimBuilderRetryActionReadRepository(
        summary=retry_action_summary or _retry_action_summary(),
    )
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork()
    result = await HandleReconcileClaimBuilderProgressCommandHandler().execute(
        HandleReconcileClaimBuilderProgressCommand(
            workflow_command=workflow_command or _workflow_command(),
        ),
        work_item_progress_read_repository=progress_repository,
        claim_builder_retry_action_read_repository=retry_action_repository,
        workflow_unit_of_work=workflow_unit_of_work,
    )
    return result, progress_repository, retry_action_repository, workflow_unit_of_work


@pytest.mark.asyncio
async def test_rejects_wrong_command_type() -> None:
    with pytest.raises(ValueError, match="command_type"):
        await _execute(
            workflow_command=_workflow_command(
                command_type=KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value,
            )
        )


@pytest.mark.asyncio
async def test_rejects_non_pending_command() -> None:
    with pytest.raises(ValueError, match="PENDING"):
        await _execute(
            workflow_command=_workflow_command(status=WorkflowCommandStatus.COMPLETED),
        )


@pytest.mark.asyncio
async def test_rejects_mismatched_workflow_run_id() -> None:
    with pytest.raises(ValueError, match="workflow_run_id"):
        await _execute(
            workflow_command=_workflow_command(
                payload_workflow_run_id="knowledge-extraction:other",
            )
        )


@pytest.mark.asyncio
async def test_ready_work_appends_prepare_dispatch_batch_now() -> None:
    result, progress_repository, _, workflow_unit_of_work = await _execute(
        summary=_summary(ready_count=1, completed_count=2),
    )

    assert result.decision == (
        ClaimBuilderProgressReconcileDecision.PREPARE_NEXT_BATCH_NOW.value
    )
    assert progress_repository.calls[0][1] == CLAIM_BUILDER_SECTION_WORK_KIND
    assert len(workflow_unit_of_work.command_log.pending_commands) == 1
    next_command = workflow_unit_of_work.command_log.pending_commands[0]
    assert next_command.command_type == (
        KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH.value
    )
    assert next_command.run_after == _now()
    assert "llm_dispatch_preparation" in next_command.payload
    assert next_command.payload["scheduled_work_item_count"] == 3
    assert "summary" not in next_command.payload
    assert "retry_action_summary" not in next_command.payload


@pytest.mark.asyncio
async def test_same_reconcile_replay_keeps_prepare_key_and_payload_stable_when_counts_change() -> (
    None
):
    workflow_command = _workflow_command()
    _, _, _, first_uow = await _execute(
        workflow_command=workflow_command,
        summary=_summary(ready_count=2, completed_count=1),
    )
    _, _, _, second_uow = await _execute(
        workflow_command=workflow_command,
        summary=_summary(ready_count=1, completed_count=2),
    )

    first_command = first_uow.command_log.pending_commands[0]
    second_command = second_uow.command_log.pending_commands[0]

    assert first_command.idempotency_key == second_command.idempotency_key
    assert dict(first_command.payload) == dict(second_command.payload)
    assert first_command.payload["scheduled_work_item_count"] == 3
    assert "summary" not in first_command.payload
    assert "retry_action_summary" not in first_command.payload


@pytest.mark.asyncio
async def test_distinct_reconcile_commands_create_distinct_prepare_keys_for_next_batches() -> (
    None
):
    _, _, _, first_uow = await _execute(
        workflow_command=_workflow_command(reconcile_ref="work-1-attempt-1"),
        summary=_summary(ready_count=2, completed_count=1),
    )
    _, _, _, second_uow = await _execute(
        workflow_command=_workflow_command(reconcile_ref="work-2-attempt-1"),
        summary=_summary(ready_count=1, completed_count=2),
    )

    first_command = first_uow.command_log.pending_commands[0]
    second_command = second_uow.command_log.pending_commands[0]

    assert first_command.idempotency_key != second_command.idempotency_key
    assert dict(first_command.payload) == dict(second_command.payload)
    assert first_command.payload["scheduled_work_item_count"] == 3


@pytest.mark.asyncio
async def test_future_retryable_work_appends_prepare_dispatch_batch_later() -> None:
    next_due_at = _now() + timedelta(minutes=2)
    result, _, _, workflow_unit_of_work = await _execute(
        summary=_summary(
            retryable_failed_count=1,
            due_retryable_failed_count=0,
            completed_count=2,
            next_due_at=next_due_at,
        ),
    )

    assert result.decision == (
        ClaimBuilderProgressReconcileDecision.PREPARE_NEXT_BATCH_LATER.value
    )
    next_command = workflow_unit_of_work.command_log.pending_commands[0]
    assert next_command.command_type == (
        KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH.value
    )
    assert next_command.run_after == next_due_at


@pytest.mark.asyncio
async def test_legacy_deferred_work_does_not_schedule_prepare_batch() -> None:
    result, _, _, workflow_unit_of_work = await _execute(
        summary=_summary(
            deferred_count=1,
            due_deferred_count=1,
            completed_count=2,
            next_due_at=_now() + timedelta(minutes=2),
        ),
    )

    assert result.decision == (
        ClaimBuilderProgressReconcileDecision.CLAIM_BUILDER_PROGRESS_BLOCKED.value
    )
    assert workflow_unit_of_work.command_log.pending_commands == []


@pytest.mark.asyncio
async def test_all_completed_appends_generate_draft_claim_embeddings() -> None:
    result, _, _, workflow_unit_of_work = await _execute(
        summary=_summary(completed_count=3),
    )

    assert result.decision == (
        ClaimBuilderProgressReconcileDecision.CLAIM_BUILDER_SECTION_EXTRACTION_DRAINED.value
    )
    next_command = workflow_unit_of_work.command_log.pending_commands[0]
    assert next_command.command_type == (
        KnowledgeExtractionCanonicalCommandType.GENERATE_DRAFT_CLAIM_EMBEDDINGS.value
    )


@pytest.mark.asyncio
async def test_appends_reconciled_event_progress_timeline_and_marks_completed() -> None:
    result, _, _, workflow_unit_of_work = await _execute(
        summary=_summary(completed_count=2, terminal_failed_count=1),
    )

    assert result.appended_event_count == 1
    assert result.appended_next_command_count == 1
    assert workflow_unit_of_work.outbox.events[0].event_type == (
        KnowledgeExtractionCanonicalEventType.CLAIM_BUILDER_PROGRESS_RECONCILED.value
    )
    assert workflow_unit_of_work.outbox.events[0].payload["decision"] == (
        ClaimBuilderProgressReconcileDecision.CLAIM_BUILDER_SECTION_EXTRACTION_DRAINED.value
    )

    snapshot = workflow_unit_of_work.progress_snapshots.snapshot
    assert snapshot is not None
    assert snapshot.total_work_items == 3
    assert snapshot.completed_work_items == 2
    assert snapshot.terminal_failed_work_items == 1
    assert snapshot.domain_counters["claim_builder_terminal_coverage_count"] == 3

    assert tuple(entry.message for entry in workflow_unit_of_work.timeline.entries) == (
        "Claim builder progress reconciled",
    )
    assert workflow_unit_of_work.command_log.completed_command_ids == [
        _workflow_command().command_id
    ]


@pytest.mark.asyncio
async def test_leased_work_without_due_items_blocks_without_next_command() -> None:
    result, _, _, workflow_unit_of_work = await _execute(
        summary=_summary(leased_count=1, completed_count=2),
    )

    assert result.decision == (
        ClaimBuilderProgressReconcileDecision.CLAIM_BUILDER_PROGRESS_BLOCKED.value
    )
    assert result.appended_next_command_count == 0
    assert workflow_unit_of_work.command_log.pending_commands == []
    assert workflow_unit_of_work.progress_snapshots.snapshot is not None
    assert (
        workflow_unit_of_work.progress_snapshots.snapshot.workflow_status == "BLOCKED"
    )


@pytest.mark.asyncio
async def test_reconcile_commands_from_same_prepare_origin_coalesce_next_prepare_identity() -> (
    None
):
    def _with_prepare_origin(command: WorkflowCommand) -> WorkflowCommand:
        payload = dict(command.payload)
        payload["claim_builder_prepare_command_id"] = (
            "workflow-command:prepare-claim-builder-dispatch-batch:origin"
        )
        payload["claim_builder_prepare_idempotency_key"] = (
            "prepare-claim-builder-dispatch-batch:origin"
        )
        return WorkflowCommand(
            command_id=command.command_id,
            command_type=command.command_type,
            workflow_run_id=command.workflow_run_id,
            idempotency_key=command.idempotency_key,
            payload=payload,
            status=command.status,
            run_after=command.run_after,
            created_at=command.created_at,
            updated_at=command.updated_at,
        )

    _, _, _, first_uow = await _execute(
        workflow_command=_with_prepare_origin(
            _workflow_command(reconcile_ref="work-1-attempt-1"),
        ),
        summary=_summary(ready_count=4),
        retry_action_summary=_retry_action_summary(),
    )
    _, _, _, second_uow = await _execute(
        workflow_command=_with_prepare_origin(
            _workflow_command(reconcile_ref="work-2-attempt-1"),
        ),
        summary=_summary(ready_count=4),
        retry_action_summary=_retry_action_summary(),
    )

    first_command = first_uow.command_log.pending_commands[0]
    second_command = second_uow.command_log.pending_commands[0]

    assert first_command.command_type == second_command.command_type
    assert first_command.workflow_run_id == second_command.workflow_run_id
    assert first_command.idempotency_key == second_command.idempotency_key
    assert first_command.payload == second_command.payload
    assert first_command.run_after == second_command.run_after


@pytest.mark.asyncio
async def test_retry_fallback_model_count_appends_prepare_with_fallback_strategy() -> (
    None
):
    result, _, retry_repository, workflow_unit_of_work = await _execute(
        summary=_summary(retryable_failed_count=1, due_retryable_failed_count=1),
        retry_action_summary=_retry_action_summary(retry_fallback_model_count=1),
    )

    assert result.decision == (
        ClaimBuilderProgressReconcileDecision.PREPARE_NEXT_BATCH_NOW.value
    )
    assert retry_repository.calls[0][1] == CLAIM_BUILDER_SECTION_WORK_KIND
    next_command = workflow_unit_of_work.command_log.pending_commands[0]
    assert next_command.payload["claim_builder_next_model_strategy"] == (
        "FALLBACK_MODEL_REQUIRED"
    )
    assert next_command.payload["llm_dispatch_preparation_strategy"] == (
        "FALLBACK_MODEL_REQUIRED"
    )
    assert next_command.payload["selected_retry_strategy"] == (
        "FALLBACK_MODEL_REQUIRED"
    )
    assert "summary" not in next_command.payload
    assert "retry_action_summary" not in next_command.payload


@pytest.mark.asyncio
async def test_retry_strategy_prepare_key_ignores_reconcile_causation() -> None:
    _, _, _, first_uow = await _execute(
        workflow_command=_workflow_command(reconcile_ref="work-1-attempt-1"),
        summary=_summary(retryable_failed_count=1, due_retryable_failed_count=1),
        retry_action_summary=_retry_action_summary(retry_fallback_model_count=1),
    )
    _, _, _, second_uow = await _execute(
        workflow_command=_workflow_command(reconcile_ref="work-2-attempt-1"),
        summary=_summary(retryable_failed_count=1, due_retryable_failed_count=1),
        retry_action_summary=_retry_action_summary(retry_fallback_model_count=1),
    )

    first_command = first_uow.command_log.pending_commands[0]
    second_command = second_uow.command_log.pending_commands[0]

    assert first_command.idempotency_key == second_command.idempotency_key
    assert first_command.payload == second_command.payload
    assert first_command.run_after == second_command.run_after
    assert first_command.payload["selected_retry_strategy"] == (
        "FALLBACK_MODEL_REQUIRED"
    )


@pytest.mark.asyncio
async def test_retry_larger_output_count_appends_prepare_with_larger_output_strategy() -> (
    None
):
    _, _, _, workflow_unit_of_work = await _execute(
        summary=_summary(retryable_failed_count=1, due_retryable_failed_count=1),
        retry_action_summary=_retry_action_summary(
            retry_larger_output_model_count=1,
        ),
    )

    next_command = workflow_unit_of_work.command_log.pending_commands[0]
    assert next_command.payload["claim_builder_next_model_strategy"] == (
        "LARGER_OUTPUT_LIMIT_MODEL_REQUIRED"
    )
    assert next_command.payload["llm_dispatch_preparation_strategy"] == (
        "LARGER_OUTPUT_LIMIT_MODEL_REQUIRED"
    )


@pytest.mark.asyncio
async def test_retry_larger_input_count_appends_prepare_with_larger_input_strategy() -> (
    None
):
    _, _, _, workflow_unit_of_work = await _execute(
        summary=_summary(retryable_failed_count=1, due_retryable_failed_count=1),
        retry_action_summary=_retry_action_summary(
            retry_larger_input_model_count=1,
        ),
    )

    next_command = workflow_unit_of_work.command_log.pending_commands[0]
    assert next_command.payload["claim_builder_next_model_strategy"] == (
        "LARGER_INPUT_LIMIT_MODEL_REQUIRED"
    )
    assert next_command.payload["llm_dispatch_preparation_strategy"] == (
        "LARGER_INPUT_LIMIT_MODEL_REQUIRED"
    )


@pytest.mark.asyncio
async def test_retry_same_model_count_appends_prepare_with_same_model_strategy() -> (
    None
):
    _, _, _, workflow_unit_of_work = await _execute(
        summary=_summary(retryable_failed_count=1, due_retryable_failed_count=1),
        retry_action_summary=_retry_action_summary(retry_same_model_count=1),
    )

    next_command = workflow_unit_of_work.command_log.pending_commands[0]
    assert next_command.payload["claim_builder_next_model_strategy"] == "SAME_MODEL"
    assert next_command.payload["llm_dispatch_preparation_strategy"] == "SAME_MODEL"


@pytest.mark.asyncio
async def test_split_required_blocks_without_prepare_command() -> None:
    result, _, _, workflow_unit_of_work = await _execute(
        summary=_summary(retryable_failed_count=1, due_retryable_failed_count=1),
        retry_action_summary=_retry_action_summary(split_required_count=1),
    )

    assert result.decision == (
        ClaimBuilderProgressReconcileDecision.CLAIM_BUILDER_SPLIT_REQUIRED.value
    )
    assert result.appended_next_command_count == 0
    assert workflow_unit_of_work.command_log.pending_commands == []
    assert (
        workflow_unit_of_work.outbox.events[0].payload["retry_action_summary"][
            "split_required_count"
        ]
        == 1
    )
    assert workflow_unit_of_work.progress_snapshots.snapshot is not None
    assert (
        workflow_unit_of_work.progress_snapshots.snapshot.domain_counters[
            "claim_builder_split_required_pending_count"
        ]
        == 1
    )


@pytest.mark.asyncio
async def test_progress_event_includes_retry_action_summary_and_selected_strategy() -> (
    None
):
    _, _, _, workflow_unit_of_work = await _execute(
        summary=_summary(retryable_failed_count=1, due_retryable_failed_count=1),
        retry_action_summary=_retry_action_summary(retry_fallback_model_count=1),
    )

    event_payload = workflow_unit_of_work.outbox.events[0].payload
    assert event_payload["selected_retry_strategy"] == "FALLBACK_MODEL_REQUIRED"
    assert event_payload["retry_action_summary"]["retry_fallback_model_count"] == 1

    snapshot = workflow_unit_of_work.progress_snapshots.snapshot
    assert snapshot is not None
    assert (
        snapshot.domain_counters["claim_builder_retry_fallback_model_pending_count"]
        == 1
    )

    assert tuple(entry.message for entry in workflow_unit_of_work.timeline.entries) == (
        "Claim builder retry action selected",
    )


@pytest.mark.asyncio
async def test_completed_path_to_embeddings_still_works_without_retry_actions() -> None:
    result, _, _, workflow_unit_of_work = await _execute(
        summary=_summary(completed_count=3),
    )

    assert result.decision == (
        ClaimBuilderProgressReconcileDecision.CLAIM_BUILDER_SECTION_EXTRACTION_DRAINED.value
    )
    next_command = workflow_unit_of_work.command_log.pending_commands[0]
    assert next_command.command_type == (
        KnowledgeExtractionCanonicalCommandType.GENERATE_DRAFT_CLAIM_EMBEDDINGS.value
    )
