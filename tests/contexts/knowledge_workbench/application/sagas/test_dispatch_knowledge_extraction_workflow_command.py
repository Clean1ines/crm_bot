from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.interfaces.composition.prepare_llm_dispatch_batch import (
    PrepareLlmDispatchBatchCommand,
)
from src.interfaces.composition.start_llm_admitted_work_item_attempts import (
    StartedLlmAdmittedAttempt,
)
from src.contexts.knowledge_workbench.application.sagas.dispatch_knowledge_extraction_workflow_command import (
    COMMAND_HANDLER_NOT_IMPLEMENTED,
    DispatchKnowledgeExtractionWorkflowCommand,
    DispatchKnowledgeExtractionWorkflowCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    operation_by_command_type,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_document import (
    SourceDocument,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.heading_path import (
    HeadingPath,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_kind import (
    SourceUnitKind,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_lineage import (
    SourceUnitLineage,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_text import (
    SourceUnitText,
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
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "knowledge-extraction:source-document:project-1:abc"


def _document_ref() -> SourceDocumentRef:
    return SourceDocumentRef("source-document:project-1:abc")


def _workflow_command(
    command_type: KnowledgeExtractionCanonicalCommandType,
) -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{command_type.value}"),
        command_type=command_type.value,
        workflow_run_id=_workflow_run_id(),
        idempotency_key=WorkflowIdempotencyKey(
            f"{command_type.value}:{_workflow_run_id()}"
        ),
        payload={
            "workflow_run_id": _workflow_run_id(),
            "source_document_ref": _document_ref().value,
            "scheduled_work_item_count": 1,
            "llm_dispatch_preparation": _dispatch_preparation(),
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


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


def _unknown_workflow_command() -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId("workflow-command:unknown"),
        command_type="UnknownCommand",
        workflow_run_id=_workflow_run_id(),
        idempotency_key=WorkflowIdempotencyKey("unknown-command"),
        payload={"workflow_run_id": _workflow_run_id()},
        status=WorkflowCommandStatus.PENDING,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


def _source_unit() -> SourceUnit:
    return SourceUnit(
        unit_ref=SourceUnitRef(f"{_document_ref().value}.unit.0"),
        document_ref=_document_ref(),
        unit_kind=SourceUnitKind.SECTION,
        text=SourceUnitText("# Unit\\n\\nBody"),
        heading_path=HeadingPath(("Unit",)),
        lineage=SourceUnitLineage(),
        ordinal=0,
        created_at=_now(),
    )


@dataclass(slots=True)
class FakeSourceManagementRepository:
    async def save_source_document(self, document: SourceDocument) -> None:
        del document

    async def load_source_document(
        self,
        document_ref: SourceDocumentRef,
    ) -> SourceDocument | None:
        del document_ref
        return None

    async def save_source_units(
        self,
        units: tuple[SourceUnit, ...],
    ) -> None:
        del units

    async def list_source_units_for_document(
        self,
        document_ref: SourceDocumentRef,
    ) -> tuple[SourceUnit, ...]:
        assert document_ref == _document_ref()
        return (_source_unit(),)

    async def load_source_unit(
        self,
        unit_ref: SourceUnitRef,
    ) -> SourceUnit | None:
        del unit_ref
        return _source_unit()


@dataclass(slots=True)
class FakeWorkItemSchedulingRepository:
    saved_count: int = 0

    async def get_work_item(self, work_item_id: str) -> WorkItem | None:
        del work_item_id
        return None

    async def get_schedule_payload_hash(self, work_item_id: str) -> str | None:
        del work_item_id
        return None

    async def save_scheduled_work_item(
        self,
        *,
        item: WorkItem,
        idempotency_key: str,
        payload_hash: str,
        payload: object,
    ) -> None:
        del item, idempotency_key, payload_hash, payload
        self.saved_count += 1


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
        return _workflow_command(
            KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK
        )

    async def list_pending_commands(
        self,
        *,
        workflow_run_id: str,
        limit: int,
    ) -> tuple[WorkflowCommand, ...]:
        del workflow_run_id, limit
        return ()


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
        default_factory=FakeCommandLogRepository
    )
    outbox: FakeOutboxRepository = field(default_factory=FakeOutboxRepository)
    event_cursors: FakeEventCursorRepository = field(
        default_factory=FakeEventCursorRepository
    )
    progress_snapshots: FakeProgressSnapshotRepository = field(
        default_factory=FakeProgressSnapshotRepository
    )
    timeline: FakeTimelineRepository = field(default_factory=FakeTimelineRepository)
    resource_usage: FakeResourceUsageRepository = field(
        default_factory=FakeResourceUsageRepository
    )

    async def commit(self) -> None:
        raise AssertionError("dispatcher must not own transaction commit")

    async def rollback(self) -> None:
        raise AssertionError("dispatcher must not own transaction rollback")


@pytest.mark.asyncio
async def test_dispatches_schedule_claim_builder_section_work_to_existing_handler() -> (
    None
):
    source_repository = FakeSourceManagementRepository()
    scheduling_repository = FakeWorkItemSchedulingRepository()
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork()

    result = await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(
            workflow_command=_workflow_command(
                KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK
            )
        ),
        source_unit_repository=source_repository,
        knowledge_unit_of_work=scheduling_repository,
        workflow_unit_of_work=workflow_unit_of_work,
    )

    operation = operation_by_command_type(
        KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK
    )
    assert result.dispatched is True
    assert result.operation_key == operation.operation_key
    assert result.phase == operation.phase.value
    assert result.handler_name == "HandleScheduleClaimBuilderSectionWorkCommandHandler"
    assert scheduling_repository.saved_count == 1


@dataclass(slots=True)
class FakeAttemptResult:
    started_attempts: tuple[StartedLlmAdmittedAttempt, ...]


@dataclass(slots=True)
class FakePrepareResult:
    attempt_result: FakeAttemptResult
    input_size_preflight_decision: str = "USE_ACTIVE_MODEL"
    input_size_preflight_reason: str = (
        "estimated prompt tokens fit active model input limit"
    )
    input_size_preflight_active_model_ref: str | None = "qwen/qwen3-32b"
    source_split_required: bool = False
    affected_work_item_refs: tuple[str, ...] = ()
    source_unit_refs: tuple[str, ...] = ()


@dataclass(slots=True)
class FakePrepareLlmDispatchBatch:
    calls: list[PrepareLlmDispatchBatchCommand] = field(default_factory=list)

    async def execute(self, command: PrepareLlmDispatchBatchCommand) -> object:
        self.calls.append(command)
        return FakePrepareResult(
            attempt_result=FakeAttemptResult(
                started_attempts=(
                    StartedLlmAdmittedAttempt(
                        attempt_id="work-1:attempt:1",
                        work_item_id="work-1",
                        attempt_number=1,
                        dispatch_payload={"work_item_id": "work-1"},
                    ),
                ),
            ),
        )


@pytest.mark.asyncio
async def test_dispatches_prepare_claim_builder_dispatch_batch_to_existing_handler() -> (
    None
):
    prepare = FakePrepareLlmDispatchBatch()
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork()

    result = await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(
            workflow_command=_workflow_command(
                KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH
            )
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=FakeWorkItemSchedulingRepository(),
        workflow_unit_of_work=workflow_unit_of_work,
        prepare_llm_dispatch_batch=prepare,
    )

    operation = operation_by_command_type(
        KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH
    )
    assert result.dispatched is True
    assert result.blocked_reason is None
    assert result.operation_key == operation.operation_key
    assert result.phase == operation.phase.value
    assert result.handler_name == "HandlePrepareClaimBuilderDispatchBatchCommandHandler"
    assert len(prepare.calls) == 1
    assert tuple(
        command.command_type
        for command in workflow_unit_of_work.command_log.pending_commands
    ) == (KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value,)


@pytest.mark.asyncio
async def test_known_unimplemented_execute_claim_builder_section_returns_blocked() -> (
    None
):
    result = await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(
            workflow_command=_workflow_command(
                KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION
            )
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=FakeWorkItemSchedulingRepository(),
        workflow_unit_of_work=FakeWorkflowRuntimeUnitOfWork(),
    )

    operation = operation_by_command_type(
        KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION
    )
    assert result.dispatched is False
    assert result.blocked_reason == COMMAND_HANDLER_NOT_IMPLEMENTED
    assert result.operation_key == operation.operation_key
    assert result.phase == operation.phase.value


@dataclass(slots=True)
class FakeDraftClaimCompactionPlanRepository:
    pass


@dataclass(slots=True)
class FakeDraftClaimCompactionReductionStateRepository:
    pass


@pytest.mark.asyncio
async def test_cluster_draft_claims_requires_reduction_state_repository() -> None:
    result = await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
        DispatchKnowledgeExtractionWorkflowCommand(
            workflow_command=_workflow_command(
                KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS
            )
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=FakeWorkItemSchedulingRepository(),
        workflow_unit_of_work=FakeWorkflowRuntimeUnitOfWork(),
        draft_claim_compaction_plan_repository=FakeDraftClaimCompactionPlanRepository(),
    )

    operation = operation_by_command_type(
        KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS
    )
    assert result.dispatched is False
    assert result.blocked_reason == COMMAND_HANDLER_NOT_IMPLEMENTED
    assert result.operation_key == operation.operation_key
    assert result.phase == operation.phase.value


@pytest.mark.asyncio
async def test_unknown_command_type_raises_value_error() -> None:
    with pytest.raises(ValueError, match="unknown knowledge extraction command type"):
        await DispatchKnowledgeExtractionWorkflowCommandHandler().execute(
            DispatchKnowledgeExtractionWorkflowCommand(
                workflow_command=_unknown_workflow_command()
            ),
            source_unit_repository=FakeSourceManagementRepository(),
            knowledge_unit_of_work=FakeWorkItemSchedulingRepository(),
            workflow_unit_of_work=FakeWorkflowRuntimeUnitOfWork(),
        )
