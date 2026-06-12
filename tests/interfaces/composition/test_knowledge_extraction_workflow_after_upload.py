from __future__ import annotations

from collections.abc import Mapping
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
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
)
from src.contexts.knowledge_workbench.application.sagas.run_source_ingestion_first_phase import (
    RunSourceIngestionFirstPhaseCommand,
    RunSourceIngestionFirstPhaseResult,
    RunSourceIngestionFirstPhaseStatus,
)
from src.contexts.knowledge_workbench.extraction.application.ports.validated_draft_claim_observation_persistence_port import (
    PersistValidatedDraftClaimObservationsResult,
    ValidatedDraftClaimObservationCandidate,
)
from src.contexts.knowledge_workbench.application.sagas.source_ingestion_admission import (
    SourceIngestionActor,
    SourceIngestionAdmissionStatus,
)
from src.contexts.knowledge_workbench.application.sagas.source_ingestion_workflow_effects import (
    BuildSourceIngestionWorkflowEffects,
    BuildSourceIngestionWorkflowEffectsCommand,
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
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_format import (
    SourceFormat,
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
from src.interfaces.composition import (
    knowledge_extraction_workflow_after_upload as composition,
)
from src.interfaces.composition.knowledge_extraction_workflow_after_upload import (
    RunKnowledgeExtractionWorkflowAfterUpload,
    RunKnowledgeExtractionWorkflowAfterUploadCommand,
)


def _now() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _workflow_run_id() -> str:
    return "knowledge-extraction:source-document:project-1:abc"


def _source_document_ref() -> SourceDocumentRef:
    return SourceDocumentRef("source-document:project-1:abc")


def _source_ingestion_command() -> RunSourceIngestionFirstPhaseCommand:
    return RunSourceIngestionFirstPhaseCommand(
        project_id="project-1",
        actor=SourceIngestionActor(actor_user_id="owner-1"),
        original_filename="knowledge.md",
        source_format=SourceFormat.MARKDOWN,
        content_bytes=b"# Knowledge",
        raw_text="# Knowledge\n\nText",
        occurred_at=_now(),
        segmentation_budget=None,
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


def _schedule_command() -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId(
            f"workflow-command:schedule-claim-builder-section-work:{_workflow_run_id()}"
        ),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK.value
        ),
        workflow_run_id=_workflow_run_id(),
        idempotency_key=WorkflowIdempotencyKey(
            f"schedule-claim-builder-section-work:{_workflow_run_id()}"
        ),
        payload={
            "workflow_run_id": _workflow_run_id(),
            "source_document_ref": _source_document_ref().value,
            "source_unit_count": 1,
            "llm_dispatch_preparation": _dispatch_preparation(),
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


def _source_unit() -> SourceUnit:
    return SourceUnit(
        unit_ref=SourceUnitRef(f"{_source_document_ref().value}.unit.0"),
        document_ref=_source_document_ref(),
        unit_kind=SourceUnitKind.SECTION,
        text=SourceUnitText("# Unit\n\nBody"),
        heading_path=HeadingPath(("Unit",)),
        lineage=SourceUnitLineage(),
        ordinal=0,
        created_at=_now(),
    )


@dataclass(slots=True)
class FakeSourceIngestionRunner:
    completed: bool = True
    calls: list[RunSourceIngestionFirstPhaseCommand] = field(default_factory=list)

    async def execute(
        self,
        command: RunSourceIngestionFirstPhaseCommand,
    ) -> RunSourceIngestionFirstPhaseResult:
        self.calls.append(command)
        if not self.completed:
            return RunSourceIngestionFirstPhaseResult(
                status=RunSourceIngestionFirstPhaseStatus.REJECTED,
                admission_status=SourceIngestionAdmissionStatus.ACTOR_ROLE_NOT_ALLOWED,
            )
        return RunSourceIngestionFirstPhaseResult(
            status=RunSourceIngestionFirstPhaseStatus.COMPLETED,
            admission_status=SourceIngestionAdmissionStatus.ALLOWED,
            workflow_run_id=_workflow_run_id(),
            source_document_ref=_source_document_ref().value,
            source_unit_count=1,
            workflow_effects=BuildSourceIngestionWorkflowEffects().execute(
                BuildSourceIngestionWorkflowEffectsCommand(
                    workflow_run_id=_workflow_run_id(),
                    project_id="project-1",
                    source_document_ref=_source_document_ref().value,
                    source_unit_count=1,
                    source_format=SourceFormat.MARKDOWN,
                    content_hash="sha256:test",
                    occurred_at=command.occurred_at,
                )
            ),
        )


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
class FakeDraftClaimObservationPersistence:
    persisted_candidates: list[tuple[ValidatedDraftClaimObservationCandidate, ...]] = (
        field(default_factory=list)
    )

    async def persist_validated_claims(
        self,
        candidates: tuple[ValidatedDraftClaimObservationCandidate, ...],
    ) -> PersistValidatedDraftClaimObservationsResult:
        self.persisted_candidates.append(candidates)
        return PersistValidatedDraftClaimObservationsResult(
            persisted_count=len(candidates),
        )


class FakePostgresValidatedDraftClaimObservationPersistence(
    FakeDraftClaimObservationPersistence
):
    instances: list["FakePostgresValidatedDraftClaimObservationPersistence"] = []

    def __init__(self, connection: object) -> None:
        if not isinstance(connection, FakeConnection):
            raise TypeError("connection must be FakeConnection")
        self.connection = connection
        super().__init__()
        FakePostgresValidatedDraftClaimObservationPersistence.instances.append(self)


@dataclass(slots=True)
class FakeCommandLogRepository:
    commands: list[WorkflowCommand] = field(
        default_factory=lambda: [_schedule_command()]
    )

    async def append_pending_command(
        self,
        command: WorkflowCommand,
    ) -> WorkflowCommand:
        self.commands.append(command)
        return command

    async def mark_command_completed(
        self,
        *,
        command_id: WorkflowCommandId,
        completed_at: datetime,
    ) -> WorkflowCommand:
        for index, command in enumerate(self.commands):
            if command.command_id == command_id:
                completed = WorkflowCommand(
                    command_id=command.command_id,
                    command_type=command.command_type,
                    workflow_run_id=command.workflow_run_id,
                    idempotency_key=command.idempotency_key,
                    payload=command.payload,
                    status=WorkflowCommandStatus.COMPLETED,
                    run_after=command.run_after,
                    created_at=command.created_at,
                    updated_at=completed_at,
                    attempt_count=command.attempt_count,
                )
                self.commands[index] = completed
                return completed
        raise KeyError(command_id.value)

    async def list_pending_commands(
        self,
        *,
        workflow_run_id: str,
        limit: int,
    ) -> tuple[WorkflowCommand, ...]:
        pending = [
            command
            for command in self.commands
            if command.workflow_run_id == workflow_run_id
            and command.status is WorkflowCommandStatus.PENDING
        ]
        pending = sorted(
            pending, key=lambda command: (command.run_after, command.created_at)
        )
        return tuple(pending[:limit])


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
class FakeConnection:
    command_log: FakeCommandLogRepository = field(
        default_factory=FakeCommandLogRepository
    )
    source_units: tuple[SourceUnit, ...] = field(
        default_factory=lambda: (_source_unit(),)
    )
    scheduled_work_item_count: int = 0


class FakePool:
    def __init__(self, connection: FakeConnection) -> None:
        self.connection = connection
        self.acquire_count = 0
        self.released_connections: list[FakeConnection] = []

    async def acquire(self) -> FakeConnection:
        self.acquire_count += 1
        return self.connection

    async def release(self, connection: object) -> None:
        if not isinstance(connection, FakeConnection):
            raise TypeError("released connection must be FakeConnection")
        self.released_connections.append(connection)


class FakePostgresWorkflowRuntimeUnitOfWork:
    instances: list[FakePostgresWorkflowRuntimeUnitOfWork] = []

    def __init__(self, connection: object) -> None:
        if not isinstance(connection, FakeConnection):
            raise TypeError("connection must be FakeConnection")
        self.connection = connection
        self.command_log = connection.command_log
        self.outbox = FakeOutboxRepository()
        self.event_cursors = FakeEventCursorRepository()
        self.progress_snapshots = FakeProgressSnapshotRepository()
        self.timeline = FakeTimelineRepository()
        self.resource_usage = FakeResourceUsageRepository()
        self.start_count = 0
        self.commit_count = 0
        self.rollback_count = 0
        FakePostgresWorkflowRuntimeUnitOfWork.instances.append(self)

    async def start(self) -> None:
        self.start_count += 1

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


class FakePostgresSourceManagementRepository:
    def __init__(self, connection: object) -> None:
        if not isinstance(connection, FakeConnection):
            raise TypeError("connection must be FakeConnection")
        self.connection = connection

    async def save_source_document(self, document: SourceDocument) -> None:
        del document

    async def load_source_document(
        self,
        document_ref: SourceDocumentRef,
    ) -> SourceDocument | None:
        del document_ref
        return None

    async def save_source_units(self, units: tuple[SourceUnit, ...]) -> None:
        self.connection.source_units = units

    async def list_source_units_for_document(
        self,
        document_ref: SourceDocumentRef,
    ) -> tuple[SourceUnit, ...]:
        assert document_ref == _source_document_ref()
        return self.connection.source_units

    async def load_source_unit(
        self,
        unit_ref: SourceUnitRef,
    ) -> SourceUnit | None:
        return next(
            (
                unit
                for unit in self.connection.source_units
                if unit.unit_ref == unit_ref
            ),
            None,
        )


class FakePostgresWorkItemSchedulingRepository:
    def __init__(self, connection: object) -> None:
        if not isinstance(connection, FakeConnection):
            raise TypeError("connection must be FakeConnection")
        self.connection = connection
        self.items: dict[str, WorkItem] = {}
        self.payload_hashes: dict[str, str] = {}

    async def get_work_item(self, work_item_id: str) -> WorkItem | None:
        return self.items.get(work_item_id)

    async def get_schedule_payload_hash(self, work_item_id: str) -> str | None:
        return self.payload_hashes.get(work_item_id)

    async def save_scheduled_work_item(
        self,
        *,
        item: WorkItem,
        idempotency_key: str,
        payload_hash: str,
        payload: Mapping[str, object],
    ) -> None:
        del idempotency_key, payload
        self.items[item.work_item_id] = item
        self.payload_hashes[item.work_item_id] = payload_hash
        self.connection.scheduled_work_item_count += 1


def _patch_drain_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    FakePostgresWorkflowRuntimeUnitOfWork.instances = []
    monkeypatch.setattr(
        composition,
        "PostgresWorkflowRuntimeUnitOfWork",
        FakePostgresWorkflowRuntimeUnitOfWork,
    )
    monkeypatch.setattr(
        composition,
        "PostgresSourceManagementRepository",
        FakePostgresSourceManagementRepository,
    )
    monkeypatch.setattr(
        composition,
        "PostgresWorkItemSchedulingRepository",
        FakePostgresWorkItemSchedulingRepository,
    )
    FakePostgresValidatedDraftClaimObservationPersistence.instances = []
    monkeypatch.setattr(
        composition,
        "PostgresValidatedDraftClaimObservationPersistence",
        FakePostgresValidatedDraftClaimObservationPersistence,
    )


@pytest.mark.asyncio
async def test_completed_source_ingestion_triggers_drain_and_blocks_on_prepare_batch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_drain_dependencies(monkeypatch)
    connection = FakeConnection()
    pool = FakePool(connection)
    source_runner = FakeSourceIngestionRunner(completed=True)

    runner = RunKnowledgeExtractionWorkflowAfterUpload(
        source_ingestion_runner=source_runner,
        pool=pool,
        prepare_llm_dispatch_batch=FakePrepareLlmDispatchBatch(),
    )
    result = await runner.execute(
        RunKnowledgeExtractionWorkflowAfterUploadCommand(
            source_ingestion_command=_source_ingestion_command(),
            max_drain_commands=10,
        )
    )

    assert result.source_ingestion_completed is True
    assert result.workflow_run_id == _workflow_run_id()
    assert result.drained_inspected_count == 3
    assert result.drained_dispatched_count == 2
    assert (
        result.blocked_command_type
        == KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value
    )
    assert result.blocked_reason == COMMAND_HANDLER_NOT_IMPLEMENTED
    assert (
        result.source_ingestion_admission_status
        is SourceIngestionAdmissionStatus.ALLOWED
    )
    assert connection.scheduled_work_item_count == 1
    assert pool.acquire_count == 3
    assert len(FakePostgresWorkflowRuntimeUnitOfWork.instances) == 3


@pytest.mark.asyncio
async def test_completed_source_ingestion_updates_command_log_states(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_drain_dependencies(monkeypatch)
    connection = FakeConnection()
    runner = RunKnowledgeExtractionWorkflowAfterUpload(
        source_ingestion_runner=FakeSourceIngestionRunner(completed=True),
        pool=FakePool(connection),
        prepare_llm_dispatch_batch=FakePrepareLlmDispatchBatch(),
    )

    await runner.execute(
        RunKnowledgeExtractionWorkflowAfterUploadCommand(
            source_ingestion_command=_source_ingestion_command(),
            max_drain_commands=10,
        )
    )

    schedule_commands = [
        command
        for command in connection.command_log.commands
        if command.command_type
        == KnowledgeExtractionCanonicalCommandType.SCHEDULE_CLAIM_BUILDER_SECTION_WORK.value
    ]
    prepare_commands = [
        command
        for command in connection.command_log.commands
        if command.command_type
        == KnowledgeExtractionCanonicalCommandType.PREPARE_CLAIM_BUILDER_DISPATCH_BATCH.value
    ]

    assert len(schedule_commands) == 1
    assert schedule_commands[0].status is WorkflowCommandStatus.COMPLETED
    execute_commands = [
        command
        for command in connection.command_log.commands
        if command.command_type
        == KnowledgeExtractionCanonicalCommandType.EXECUTE_CLAIM_BUILDER_SECTION.value
    ]

    assert len(prepare_commands) == 1
    assert prepare_commands[0].status is WorkflowCommandStatus.COMPLETED
    assert len(execute_commands) == 1
    assert execute_commands[0].status is WorkflowCommandStatus.PENDING


@pytest.mark.asyncio
async def test_rejected_source_ingestion_does_not_run_drain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_drain_dependencies(monkeypatch)
    connection = FakeConnection()
    pool = FakePool(connection)
    source_runner = FakeSourceIngestionRunner(completed=False)

    runner = RunKnowledgeExtractionWorkflowAfterUpload(
        source_ingestion_runner=source_runner,
        pool=pool,
        prepare_llm_dispatch_batch=FakePrepareLlmDispatchBatch(),
    )
    result = await runner.execute(
        RunKnowledgeExtractionWorkflowAfterUploadCommand(
            source_ingestion_command=_source_ingestion_command(),
            max_drain_commands=10,
        )
    )

    assert result.source_ingestion_completed is False
    assert result.drained_inspected_count == 0
    assert result.drained_dispatched_count == 0
    assert result.blocked_command_type is None
    assert result.blocked_reason is None
    assert result.source_ingestion_admission_status is (
        SourceIngestionAdmissionStatus.ACTOR_ROLE_NOT_ALLOWED
    )
    assert pool.acquire_count == 0
    assert FakePostgresWorkflowRuntimeUnitOfWork.instances == []


@pytest.mark.asyncio
async def test_rejected_source_ingestion_preserves_admission_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_drain_dependencies(monkeypatch)
    runner = RunKnowledgeExtractionWorkflowAfterUpload(
        source_ingestion_runner=FakeSourceIngestionRunner(completed=False),
        pool=FakePool(FakeConnection()),
    )

    result = await runner.execute(
        RunKnowledgeExtractionWorkflowAfterUploadCommand(
            source_ingestion_command=_source_ingestion_command(),
            max_drain_commands=10,
        )
    )

    assert result.source_ingestion_completed is False
    assert result.source_ingestion_admission_status is (
        SourceIngestionAdmissionStatus.ACTOR_ROLE_NOT_ALLOWED
    )


@pytest.mark.asyncio
async def test_after_upload_passes_provided_draft_claim_observation_persistence_into_drain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_drain_dependencies(monkeypatch)
    connection = FakeConnection()
    provided_persistence = FakeDraftClaimObservationPersistence()

    runner = RunKnowledgeExtractionWorkflowAfterUpload(
        source_ingestion_runner=FakeSourceIngestionRunner(completed=True),
        pool=FakePool(connection),
        prepare_llm_dispatch_batch=FakePrepareLlmDispatchBatch(),
        draft_claim_observation_persistence=provided_persistence,
    )

    await runner.execute(
        RunKnowledgeExtractionWorkflowAfterUploadCommand(
            source_ingestion_command=_source_ingestion_command(),
            max_drain_commands=10,
        )
    )

    assert FakePostgresValidatedDraftClaimObservationPersistence.instances == []


@pytest.mark.asyncio
async def test_after_upload_constructs_postgres_draft_claim_observation_persistence_when_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_drain_dependencies(monkeypatch)
    connection = FakeConnection()

    runner = RunKnowledgeExtractionWorkflowAfterUpload(
        source_ingestion_runner=FakeSourceIngestionRunner(completed=True),
        pool=FakePool(connection),
        prepare_llm_dispatch_batch=FakePrepareLlmDispatchBatch(),
    )

    await runner.execute(
        RunKnowledgeExtractionWorkflowAfterUploadCommand(
            source_ingestion_command=_source_ingestion_command(),
            max_drain_commands=10,
        )
    )

    assert FakePostgresValidatedDraftClaimObservationPersistence.instances
    assert all(
        instance.connection is connection
        for instance in FakePostgresValidatedDraftClaimObservationPersistence.instances
    )
