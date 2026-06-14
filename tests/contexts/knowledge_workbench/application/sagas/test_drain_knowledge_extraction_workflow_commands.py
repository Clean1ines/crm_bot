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
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_compaction_output_validator import (
    DraftClaimCompactionOutputValidator,
)
from src.contexts.knowledge_workbench.application.sagas.drain_knowledge_extraction_workflow_commands import (
    WORKFLOW_MANUALLY_PAUSED,
    DrainKnowledgeExtractionWorkflowCommands,
    DrainKnowledgeExtractionWorkflowCommandsCommand,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionPhaseKey,
    KnowledgeExtractionWorkflowState,
    KnowledgeExtractionWorkflowStatus,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
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
class FakeWorkflowStateRepository:
    state: KnowledgeExtractionWorkflowState | None = None

    async def load_workflow_state(
        self,
        workflow_run_id: str,
    ) -> KnowledgeExtractionWorkflowState | None:
        assert workflow_run_id == _workflow_run_id()
        return self.state

    async def save_workflow_state(
        self,
        state: KnowledgeExtractionWorkflowState,
    ) -> None:
        self.state = state


def _workflow_state(
    status: KnowledgeExtractionWorkflowStatus,
) -> KnowledgeExtractionWorkflowState:
    return KnowledgeExtractionWorkflowState(
        workflow_run_id=_workflow_run_id(),
        project_id="project-1",
        source_document_ref=_document_ref().value,
        status=status,
        current_phase=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
        pause_reason="manual_pause"
        if status is KnowledgeExtractionWorkflowStatus.PAUSED
        else None,
        created_at=_now(),
        updated_at=_now(),
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
    pending_commands: tuple[WorkflowCommand, ...]
    requested_limit: int | None = None
    completed_command_ids: list[WorkflowCommandId] = field(default_factory=list)
    appended_pending_commands: list[WorkflowCommand] = field(default_factory=list)

    async def append_pending_command(
        self,
        command: WorkflowCommand,
    ) -> WorkflowCommand:
        self.appended_pending_commands.append(command)
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
        assert workflow_run_id == _workflow_run_id()
        self.requested_limit = limit
        return self.pending_commands[:limit]


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


@dataclass(slots=True)
class FakeWorkflowRuntimeUnitOfWork:
    command_log: FakeCommandLogRepository
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
        raise AssertionError("drain must not own transaction commit")

    async def rollback(self) -> None:
        raise AssertionError("drain must not own transaction rollback")


async def _drain(
    *,
    pending_commands: tuple[WorkflowCommand, ...],
    max_commands: int = 10,
    workflow_state_repository: FakeWorkflowStateRepository | None = None,
) -> tuple[object, FakeWorkItemSchedulingRepository, FakeWorkflowRuntimeUnitOfWork]:
    scheduling_repository = FakeWorkItemSchedulingRepository()
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork(
        command_log=FakeCommandLogRepository(pending_commands=pending_commands)
    )
    result = await DrainKnowledgeExtractionWorkflowCommands().execute(
        DrainKnowledgeExtractionWorkflowCommandsCommand(
            workflow_run_id=_workflow_run_id(),
            max_commands=max_commands,
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=scheduling_repository,
        workflow_unit_of_work=workflow_unit_of_work,
        prepare_llm_dispatch_batch=FakePrepareLlmDispatchBatch(),
        workflow_state_repository=workflow_state_repository,
    )
    return result, scheduling_repository, workflow_unit_of_work


@pytest.mark.asyncio
async def test_drains_implemented_schedule_claim_builder_section_work_command() -> None:
    result, scheduling_repository, workflow_unit_of_work = await _drain(
        pending_commands=(
            _workflow_command(
                KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK
            ),
        )
    )

    assert result.inspected_count == 1
    assert result.dispatched_count == 1
    assert result.blocked_count == 0
    assert scheduling_repository.saved_count == 1
    assert len(workflow_unit_of_work.command_log.completed_command_ids) == 1


@pytest.mark.asyncio
async def test_stops_on_execute_claim_builder_section_as_not_implemented() -> None:
    result, _, workflow_unit_of_work = await _drain(
        pending_commands=(
            _workflow_command(
                KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH
            ),
            _workflow_command(
                KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION
            ),
        )
    )

    assert result.inspected_count == 2
    assert result.dispatched_count == 1
    assert result.blocked_count == 1
    assert (
        result.last_blocked_command_type
        == KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value
    )
    assert result.last_blocked_reason == COMMAND_HANDLER_NOT_IMPLEMENTED
    assert len(workflow_unit_of_work.command_log.completed_command_ids) == 1


@pytest.mark.asyncio
async def test_respects_max_commands() -> None:
    first = _workflow_command(
        KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK
    )
    second = _workflow_command(
        KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK
    )

    result, _, workflow_unit_of_work = await _drain(
        pending_commands=(first, second),
        max_commands=1,
    )

    assert result.inspected_count == 1
    assert result.dispatched_count == 1
    assert workflow_unit_of_work.command_log.requested_limit == 1


@pytest.mark.asyncio
async def test_drain_does_not_dispatch_or_consume_pending_command_when_workflow_paused() -> (
    None
):
    pending_command = _workflow_command(
        KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH
    )
    result, scheduling_repository, workflow_unit_of_work = await _drain(
        pending_commands=(pending_command,),
        workflow_state_repository=FakeWorkflowStateRepository(
            state=_workflow_state(KnowledgeExtractionWorkflowStatus.PAUSED),
        ),
    )

    assert result.inspected_count == 1
    assert result.dispatched_count == 0
    assert result.blocked_count == 1
    assert (
        result.last_blocked_command_type
        == KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH.value
    )
    assert result.last_blocked_reason == WORKFLOW_MANUALLY_PAUSED
    assert pending_command.status is WorkflowCommandStatus.PENDING
    assert scheduling_repository.saved_count == 0
    assert workflow_unit_of_work.command_log.completed_command_ids == []


def _draft_claim_compaction_workflow_command() -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId(
            "workflow-command:PrepareDraftClaimCompactionDispatchBatch"
        ),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH.value
        ),
        workflow_run_id=_workflow_run_id(),
        idempotency_key=WorkflowIdempotencyKey(
            f"PrepareDraftClaimCompactionDispatchBatch:{_workflow_run_id()}"
        ),
        payload={
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
                "lease_token_prefix": (
                    f"draft-claim-compaction-dispatch:{_workflow_run_id()}"
                ),
                "lease_ttl_seconds": 300,
            },
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


@pytest.mark.asyncio
async def test_drains_prepare_draft_claim_compaction_dispatch_batch_command() -> None:
    result, _, workflow_unit_of_work = await _drain(
        pending_commands=(_draft_claim_compaction_workflow_command(),)
    )

    assert result.inspected_count == 1
    assert result.dispatched_count == 1
    assert result.blocked_count == 0
    assert len(workflow_unit_of_work.command_log.completed_command_ids) == 1


@pytest.mark.asyncio
async def test_drain_blocks_prepare_draft_claim_compaction_dispatch_without_dependency() -> (
    None
):
    scheduling_repository = FakeWorkItemSchedulingRepository()
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork(
        command_log=FakeCommandLogRepository(
            pending_commands=(_draft_claim_compaction_workflow_command(),)
        )
    )

    result = await DrainKnowledgeExtractionWorkflowCommands().execute(
        DrainKnowledgeExtractionWorkflowCommandsCommand(
            workflow_run_id=_workflow_run_id(),
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=scheduling_repository,
        workflow_unit_of_work=workflow_unit_of_work,
    )

    assert result.inspected_count == 1
    assert result.dispatched_count == 0
    assert result.blocked_count == 1
    assert (
        result.last_blocked_command_type
        == KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH.value
    )
    assert result.last_blocked_reason == COMMAND_HANDLER_NOT_IMPLEMENTED


def _execute_draft_claim_compaction_workflow_command() -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId("workflow-command:ExecuteDraftClaimCompaction"),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.EXECUTE_DRAFT_CLAIM_COMPACTION.value
        ),
        workflow_run_id=_workflow_run_id(),
        idempotency_key=WorkflowIdempotencyKey(
            f"ExecuteDraftClaimCompaction:{_workflow_run_id()}"
        ),
        payload={
            "workflow_run_id": _workflow_run_id(),
            "dispatch_attempt_id": "attempt-1",
            "work_item_id": "work-item-1",
            "group_ref": "group-1",
            "batch_ref": "batch-1",
            "round_index": 0,
            "expected_output_kind": "compacted_claims",
            "source_claim_refs": ["claim-a", "claim-b"],
            "left_node_ref": "raw:workflow-1:group-1:claim-a",
            "right_node_ref": "raw:workflow-1:group-1:claim-b",
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


@dataclass(slots=True)
class FakeExecutePreparedLlmDispatchAttempt:
    calls: int = 0

    async def execute(self, command) -> object:
        del command
        self.calls += 1
        raise RuntimeError("fake execute should not be reached in drain wiring tests")


@dataclass(slots=True)
class FakeCapacityObservationRepository:
    observations: list[object] = field(default_factory=list)

    async def record_observation(self, observation) -> None:
        self.observations.append(observation)


@pytest.mark.asyncio
async def test_drain_blocks_execute_draft_claim_compaction_without_validator() -> None:
    scheduling_repository = FakeWorkItemSchedulingRepository()
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork(
        command_log=FakeCommandLogRepository(
            pending_commands=(_execute_draft_claim_compaction_workflow_command(),)
        )
    )

    result = await DrainKnowledgeExtractionWorkflowCommands().execute(
        DrainKnowledgeExtractionWorkflowCommandsCommand(
            workflow_run_id=_workflow_run_id(),
        ),
        source_unit_repository=FakeSourceManagementRepository(),
        knowledge_unit_of_work=scheduling_repository,
        workflow_unit_of_work=workflow_unit_of_work,
        execute_prepared_llm_dispatch_attempt=FakeExecutePreparedLlmDispatchAttempt(),
        capacity_observation_repository=FakeCapacityObservationRepository(),
    )

    assert result.inspected_count == 1
    assert result.dispatched_count == 0
    assert result.blocked_count == 1
    assert (
        result.last_blocked_command_type
        == KnowledgeExtractionCanonicalCommandType.EXECUTE_DRAFT_CLAIM_COMPACTION.value
    )
    assert result.last_blocked_reason == COMMAND_HANDLER_NOT_IMPLEMENTED


@pytest.mark.asyncio
async def test_drain_wires_execute_draft_claim_compaction_dependencies() -> None:
    scheduling_repository = FakeWorkItemSchedulingRepository()
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork(
        command_log=FakeCommandLogRepository(
            pending_commands=(_execute_draft_claim_compaction_workflow_command(),)
        )
    )
    execute_dependency = FakeExecutePreparedLlmDispatchAttempt()

    with pytest.raises(RuntimeError, match="fake execute should not be reached"):
        await DrainKnowledgeExtractionWorkflowCommands().execute(
            DrainKnowledgeExtractionWorkflowCommandsCommand(
                workflow_run_id=_workflow_run_id(),
            ),
            source_unit_repository=FakeSourceManagementRepository(),
            knowledge_unit_of_work=scheduling_repository,
            workflow_unit_of_work=workflow_unit_of_work,
            execute_prepared_llm_dispatch_attempt=execute_dependency,
            capacity_observation_repository=FakeCapacityObservationRepository(),
            draft_claim_compaction_output_validator=DraftClaimCompactionOutputValidator(),
        )

    assert execute_dependency.calls == 1


def _execute_draft_claim_compaction_payload() -> dict[str, object]:
    return {
        "workflow_run_id": _workflow_run_id(),
        "dispatch_attempt_id": "attempt-1",
        "work_item_id": "work-item-1",
        "group_ref": "group-1",
        "batch_ref": "batch-1",
        "round_index": 0,
        "expected_output_kind": "compacted_claims",
        "source_claim_refs": ["claim-a", "claim-b"],
        "left_node_ref": "raw:workflow-1:group-1:claim-a",
        "right_node_ref": "raw:workflow-1:group-1:claim-b",
    }


def _apply_draft_claim_compaction_payload() -> dict[str, object]:
    return {
        "workflow_run_id": _workflow_run_id(),
        "group_ref": "group-1",
        "batch_ref": "batch-1",
        "work_item_id": "work-item-1",
        "round_index": 0,
        "output_kind": "compacted_claims",
        "left_node_ref": "raw:workflow-1:group-1:claim-a",
        "right_node_ref": "raw:workflow-1:group-1:claim-b",
        "compacted_claims": [
            {
                "key": "refund_support",
                "claim": "Product supports refunds.",
                "claim_kind": "capability",
                "granularity": "atomic",
                "source_claim_refs": ["claim-a", "claim-b"],
                "triples": [
                    {
                        "subject": "Product",
                        "predicate": "has_capability",
                        "object": "refunds",
                        "qualifiers": [],
                    }
                ],
                "merge_decision": "merged",
            }
        ],
        "reduced_rewrite": None,
    }


def _reconcile_draft_claim_compaction_payload() -> dict[str, object]:
    return {
        "workflow_run_id": _workflow_run_id(),
        "group_ref": "group-1",
        "caused_by_command_id": "workflow-command:apply",
    }


def _compaction_workflow_command(
    command_type: KnowledgeExtractionCanonicalCommandType,
) -> WorkflowCommand:
    payload: dict[str, object]
    if (
        command_type
        is KnowledgeExtractionCanonicalCommandType.EXECUTE_DRAFT_CLAIM_COMPACTION
    ):
        payload = _execute_draft_claim_compaction_payload()
    elif (
        command_type
        is KnowledgeExtractionCanonicalCommandType.APPLY_DRAFT_CLAIM_COMPACTION_RESULT
    ):
        payload = _apply_draft_claim_compaction_payload()
    elif (
        command_type
        is KnowledgeExtractionCanonicalCommandType.RECONCILE_DRAFT_CLAIM_COMPACTION_PROGRESS
    ):
        payload = _reconcile_draft_claim_compaction_payload()
    else:
        payload = {
            "workflow_run_id": _workflow_run_id(),
            "source_document_ref": _document_ref().value,
            "scheduled_work_item_count": 1,
            "llm_dispatch_preparation": _dispatch_preparation(),
        }

    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{command_type.value}"),
        command_type=command_type.value,
        workflow_run_id=_workflow_run_id(),
        idempotency_key=WorkflowIdempotencyKey(
            f"{command_type.value}:{_workflow_run_id()}"
        ),
        payload=payload,
        status=WorkflowCommandStatus.PENDING,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


@pytest.mark.parametrize(
    "command_type",
    (
        KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH,
        KnowledgeExtractionCanonicalCommandType.EXECUTE_DRAFT_CLAIM_COMPACTION,
        KnowledgeExtractionCanonicalCommandType.APPLY_DRAFT_CLAIM_COMPACTION_RESULT,
        KnowledgeExtractionCanonicalCommandType.RECONCILE_DRAFT_CLAIM_COMPACTION_PROGRESS,
    ),
)
@pytest.mark.asyncio
async def test_paused_workflow_blocks_draft_claim_compaction_commands(
    command_type: KnowledgeExtractionCanonicalCommandType,
) -> None:
    pending_command = _compaction_workflow_command(command_type)

    result, scheduling_repository, workflow_unit_of_work = await _drain(
        pending_commands=(pending_command,),
        workflow_state_repository=FakeWorkflowStateRepository(
            state=_workflow_state(KnowledgeExtractionWorkflowStatus.PAUSED),
        ),
    )

    assert result.inspected_count == 1
    assert result.dispatched_count == 0
    assert result.blocked_count == 1
    assert result.last_blocked_command_type == command_type.value
    assert result.last_blocked_reason == WORKFLOW_MANUALLY_PAUSED
    assert scheduling_repository.saved_count == 0
    assert workflow_unit_of_work.command_log.completed_command_ids == []


@pytest.mark.asyncio
async def test_running_workflow_drains_existing_prepare_compaction_command_after_resume() -> (
    None
):
    pending_command = _compaction_workflow_command(
        KnowledgeExtractionCanonicalCommandType.PREPARE_DRAFT_CLAIM_COMPACTION_DISPATCH_BATCH
    )

    result, _, workflow_unit_of_work = await _drain(
        pending_commands=(pending_command,),
        workflow_state_repository=FakeWorkflowStateRepository(
            state=_workflow_state(KnowledgeExtractionWorkflowStatus.RUNNING),
        ),
    )

    assert result.inspected_count == 1
    assert result.dispatched_count == 1
    assert result.blocked_count == 0
    assert workflow_unit_of_work.command_log.completed_command_ids == [
        pending_command.command_id
    ]
