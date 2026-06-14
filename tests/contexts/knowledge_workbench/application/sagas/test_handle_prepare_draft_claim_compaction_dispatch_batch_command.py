from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.application.sagas.handle_prepare_draft_claim_compaction_dispatch_batch_command import (
    DRAFT_CLAIM_COMPACTION_WORK_KIND,
    HandlePrepareDraftClaimCompactionDispatchBatchCommand,
    HandlePrepareDraftClaimCompactionDispatchBatchCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
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
from src.interfaces.composition.prepare_llm_dispatch_batch import (
    PrepareLlmDispatchBatchCommand,
)
from src.interfaces.composition.start_llm_admitted_work_item_attempts import (
    StartedLlmAdmittedAttempt,
)


def _now() -> datetime:
    return datetime(2026, 6, 14, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "workflow-1"


def _command(
    *,
    payload: dict[str, object] | None = None,
    status: WorkflowCommandStatus = WorkflowCommandStatus.PENDING,
    command_type: KnowledgeExtractionCanonicalCommandType = (
        KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH
    ),
) -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{command_type.value}"),
        command_type=command_type.value,
        workflow_run_id=_workflow_run_id(),
        idempotency_key=WorkflowIdempotencyKey(f"{command_type.value}:workflow-1"),
        payload=payload or _payload(),
        status=status,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


def _payload() -> dict[str, object]:
    return {
        "workflow_run_id": _workflow_run_id(),
        "scheduled_work_item_count": 1,
        "llm_dispatch_preparation": {
            "profile": {
                "profile_id": "draft_claim_compaction",
                "estimated_prompt_tokens": 90000,
                "estimated_completion_tokens": 4000,
                "estimated_requests": 1,
            },
            "account_capacities": (
                {
                    "provider": "groq",
                    "account_ref": "groq_org_primary",
                    "model_ref": "openai/gpt-oss-120b",
                    "remaining_minute_requests": 1,
                    "remaining_minute_tokens": 100000,
                    "remaining_daily_requests": 100,
                    "remaining_daily_tokens": 1000000,
                },
            ),
            "active_model_ref": "openai/gpt-oss-120b",
            "requested_items": 1,
            "worker_ref": "knowledge-workbench-draft-claim-compaction-dispatch",
            "lease_token_prefix": "draft-claim-compaction-dispatch:workflow-1",
            "lease_ttl_seconds": 300,
        },
    }


@dataclass(slots=True)
class FakeAttemptResult:
    started_attempts: tuple[StartedLlmAdmittedAttempt, ...]


@dataclass(slots=True)
class FakePrepareResult:
    attempt_result: FakeAttemptResult
    input_size_preflight_decision: str = "USE_ACTIVE_MODEL"
    input_size_preflight_reason: str = "input size preflight used active model"
    input_size_preflight_active_model_ref: str | None = "openai/gpt-oss-120b"
    source_split_required: bool = False
    affected_work_item_refs: tuple[str, ...] = ()
    source_unit_refs: tuple[str, ...] = ()


@dataclass(slots=True)
class FakePrepareLlmDispatchBatch:
    started_attempts: tuple[StartedLlmAdmittedAttempt, ...]
    calls: list[PrepareLlmDispatchBatchCommand] = field(default_factory=list)

    async def execute(self, command: PrepareLlmDispatchBatchCommand) -> object:
        self.calls.append(command)
        return FakePrepareResult(
            attempt_result=FakeAttemptResult(started_attempts=self.started_attempts)
        )


@dataclass(slots=True)
class FakeCommandLog:
    completed: list[WorkflowCommandId] = field(default_factory=list)

    async def append_pending_command(self, command: WorkflowCommand) -> WorkflowCommand:
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
async def test_prepares_dispatch_batch_event_progress_timeline_and_completion() -> None:
    prepare = FakePrepareLlmDispatchBatch(
        started_attempts=(
            StartedLlmAdmittedAttempt(
                attempt_id="attempt-1",
                work_item_id="work-item-1",
                attempt_number=1,
                dispatch_payload={"work_item_id": "work-item-1"},
            ),
        )
    )
    workflow_uow = FakeWorkflowUnitOfWork()

    result = (
        await HandlePrepareDraftClaimCompactionDispatchBatchCommandHandler().execute(
            HandlePrepareDraftClaimCompactionDispatchBatchCommand(
                workflow_command=_command()
            ),
            prepare_llm_dispatch_batch=prepare,
            workflow_unit_of_work=workflow_uow,
        )
    )

    assert result.prepared_dispatch_count == 1
    assert result.appended_event_count == 1
    assert result.appended_next_command_count == 0
    assert prepare.calls[0].work_kind == DRAFT_CLAIM_COMPACTION_WORK_KIND
    assert prepare.calls[0].active_model_ref == "openai/gpt-oss-120b"
    assert workflow_uow.outbox.events[0].event_type == (
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH_PREPARED.value
    )
    assert workflow_uow.progress_snapshots.snapshot is not None
    assert workflow_uow.timeline.entries[0].message == (
        "Draft claim compaction dispatch batch prepared"
    )
    assert workflow_uow.command_log.completed == [_command().command_id]


@pytest.mark.asyncio
async def test_zero_attempts_completes_without_prepared_event_or_timeline() -> None:
    prepare = FakePrepareLlmDispatchBatch(started_attempts=())
    workflow_uow = FakeWorkflowUnitOfWork()

    result = (
        await HandlePrepareDraftClaimCompactionDispatchBatchCommandHandler().execute(
            HandlePrepareDraftClaimCompactionDispatchBatchCommand(
                workflow_command=_command()
            ),
            prepare_llm_dispatch_batch=prepare,
            workflow_unit_of_work=workflow_uow,
        )
    )

    assert result.prepared_dispatch_count == 0
    assert result.appended_event_count == 0
    assert workflow_uow.outbox.events == []
    assert workflow_uow.timeline.entries == []
    assert workflow_uow.progress_snapshots.snapshot is not None
    assert workflow_uow.command_log.completed == [_command().command_id]


@pytest.mark.asyncio
async def test_empty_account_capacity_completes_without_prepare_call() -> None:
    payload = _payload()
    preparation_value = payload["llm_dispatch_preparation"]
    assert isinstance(preparation_value, dict)
    preparation = dict(preparation_value)
    preparation["account_capacities"] = ()
    payload["llm_dispatch_preparation"] = preparation
    prepare = FakePrepareLlmDispatchBatch(started_attempts=())
    workflow_uow = FakeWorkflowUnitOfWork()

    result = (
        await HandlePrepareDraftClaimCompactionDispatchBatchCommandHandler().execute(
            HandlePrepareDraftClaimCompactionDispatchBatchCommand(
                workflow_command=_command(payload=payload)
            ),
            prepare_llm_dispatch_batch=prepare,
            workflow_unit_of_work=workflow_uow,
        )
    )

    assert result.prepared_dispatch_count == 0
    assert prepare.calls == []
    assert workflow_uow.progress_snapshots.snapshot is not None
    assert workflow_uow.command_log.completed == [_command().command_id]


@pytest.mark.asyncio
async def test_rejects_wrong_command_type() -> None:
    with pytest.raises(ValueError, match="PrepareDraftClaimCompactionDispatchBatch"):
        await HandlePrepareDraftClaimCompactionDispatchBatchCommandHandler().execute(
            HandlePrepareDraftClaimCompactionDispatchBatchCommand(
                workflow_command=_command(
                    command_type=KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS
                )
            ),
            prepare_llm_dispatch_batch=FakePrepareLlmDispatchBatch(started_attempts=()),
            workflow_unit_of_work=FakeWorkflowUnitOfWork(),
        )


@pytest.mark.asyncio
async def test_rejects_non_pending_command() -> None:
    with pytest.raises(ValueError, match="PENDING"):
        await HandlePrepareDraftClaimCompactionDispatchBatchCommandHandler().execute(
            HandlePrepareDraftClaimCompactionDispatchBatchCommand(
                workflow_command=_command(status=WorkflowCommandStatus.COMPLETED)
            ),
            prepare_llm_dispatch_batch=FakePrepareLlmDispatchBatch(started_attempts=()),
            workflow_unit_of_work=FakeWorkflowUnitOfWork(),
        )
