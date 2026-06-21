from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import inspect

import pytest

from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationRequest,
    EmbeddingGenerationResult,
)
from src.contexts.knowledge_workbench.application.sagas.handle_generate_draft_claim_embeddings_command import (
    HandleGenerateDraftClaimEmbeddingsCommand,
    HandleGenerateDraftClaimEmbeddingsCommandHandler,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_embedding_input_builder import (
    DraftClaimEmbeddingInputBuilder,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_embedding_persistence_port import (
    DraftClaimEmbeddingCandidate,
    PersistDraftClaimEmbeddingsResult,
)
from src.contexts.knowledge_workbench.extraction.domain.entities.draft_claim_observation import (
    DraftClaimObservation,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_granularity import (
    DraftClaimGranularity,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_observation_ref import (
    DraftClaimObservationRef,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.draft_claim_text import (
    DraftClaimText,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.evidence_block import (
    EvidenceBlock,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.exclusion_scope import (
    ExclusionScope,
)
from src.contexts.knowledge_workbench.extraction.domain.value_objects.possible_question import (
    PossibleQuestion,
)
from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.application.projectors.knowledge_extraction_frontend_workflow_event_projector import (
    KnowledgeExtractionFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
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

EMBEDDING_MODEL_ID = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIMENSIONS = 384


def _now() -> datetime:
    return datetime(2026, 6, 14, 12, 0, tzinfo=UTC)


def _workflow_run_id() -> str:
    return "knowledge-extraction:source-document:project-1:abc"


def _workflow_command() -> WorkflowCommand:
    return WorkflowCommand(
        command_id=WorkflowCommandId(
            "workflow-command:generate-draft-claim-embeddings:workflow-1"
        ),
        command_type=(
            KnowledgeExtractionCanonicalCommandType.GENERATE_DRAFT_CLAIM_EMBEDDINGS.value
        ),
        workflow_run_id=_workflow_run_id(),
        idempotency_key=WorkflowIdempotencyKey(
            f"generate-draft-claim-embeddings:{_workflow_run_id()}"
        ),
        payload={
            "workflow_run_id": _workflow_run_id(),
            "source_document_ref": "source-document:project-1:abc",
        },
        status=WorkflowCommandStatus.PENDING,
        run_after=_now(),
        created_at=_now(),
        updated_at=_now(),
    )


def _observation(ref: str) -> DraftClaimObservation:
    return DraftClaimObservation(
        observation_ref=DraftClaimObservationRef(ref),
        source_unit_ref=SourceUnitRef("source-document:project-1:abc.unit.0"),
        claim=DraftClaimText("Product supports refunds"),
        granularity=DraftClaimGranularity.ATOMIC,
        possible_questions=(PossibleQuestion("Does product support refunds?"),),
        exclusion_scope=ExclusionScope(""),
        evidence_block=EvidenceBlock("supports refunds"),
        created_at=_now(),
    )


@dataclass(slots=True)
class FakeDraftClaimEmbeddingReadRepository:
    observations: tuple[DraftClaimObservation, ...] = ()

    async def list_unembedded_claim_observations_by_workflow_run_id(
        self,
        *,
        workflow_run_id: str,
        embedding_model_id: str,
        limit: int,
    ) -> tuple[DraftClaimObservation, ...]:
        del workflow_run_id, embedding_model_id, limit
        return self.observations


@dataclass(slots=True)
class FakeDraftClaimEmbeddingPersistence:
    result: PersistDraftClaimEmbeddingsResult = field(
        default_factory=lambda: PersistDraftClaimEmbeddingsResult(
            requested_count=0,
            inserted_count=0,
            already_exists_count=0,
        )
    )

    async def persist_draft_claim_embeddings(
        self,
        candidates: tuple[DraftClaimEmbeddingCandidate, ...],
    ) -> PersistDraftClaimEmbeddingsResult:
        del candidates
        return self.result


@dataclass(slots=True)
class FakeEmbeddingGenerationPort:
    async def embed(
        self,
        request: EmbeddingGenerationRequest,
    ) -> EmbeddingGenerationResult:
        return EmbeddingGenerationResult(
            embeddings=tuple(
                (0.1,) * request.expected_dimensions for _ in request.texts
            ),
            model_id=request.model_id,
            dimensions=request.expected_dimensions,
        )


@dataclass(slots=True)
class FakeOutboxRepository:
    events: list[WorkflowEvent] = field(default_factory=list)
    _next_sequence_number: int = 1

    async def append_event(self, event: WorkflowEvent) -> WorkflowEvent:
        persisted_event = WorkflowEvent(
            event_id=event.event_id,
            event_type=event.event_type,
            workflow_run_id=event.workflow_run_id,
            payload=event.payload,
            occurred_at=event.occurred_at,
            sequence_number=self._next_sequence_number,
            causation_command_id=event.causation_command_id,
            correlation_id=event.correlation_id,
        )
        self.events.append(persisted_event)
        self._next_sequence_number += 1
        return persisted_event

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
        return _workflow_command()


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


@dataclass(slots=True)
class InMemoryFrontendWorkflowEventRepository:
    events: dict[str, FrontendWorkflowEvent] = field(default_factory=dict)

    async def append(self, event: FrontendWorkflowEvent) -> FrontendWorkflowEvent:
        existing = self.events.get(event.projection_event_id)
        if existing is not None:
            return existing
        self.events[event.projection_event_id] = event
        return event


async def _execute(
    *,
    observations: tuple[DraftClaimObservation, ...] = (_observation("obs-1"),),
    persistence_result: PersistDraftClaimEmbeddingsResult | None = None,
    frontend_event_projection_writer: ProjectFrontendWorkflowEvent | None = None,
) -> tuple[object, FakeWorkflowRuntimeUnitOfWork]:
    workflow_unit_of_work = FakeWorkflowRuntimeUnitOfWork()
    result = await HandleGenerateDraftClaimEmbeddingsCommandHandler(
        input_builder=DraftClaimEmbeddingInputBuilder(),
    ).execute(
        HandleGenerateDraftClaimEmbeddingsCommand(
            workflow_command=_workflow_command(),
        ),
        draft_claim_embedding_read_repository=FakeDraftClaimEmbeddingReadRepository(
            observations=observations,
        ),
        draft_claim_embedding_persistence=FakeDraftClaimEmbeddingPersistence(
            result=persistence_result
            or PersistDraftClaimEmbeddingsResult(
                requested_count=len(observations),
                inserted_count=len(observations),
                already_exists_count=0,
            ),
        ),
        embedding_generation_port=FakeEmbeddingGenerationPort(),
        embedding_model_id=EMBEDDING_MODEL_ID,
        embedding_dimensions=EMBEDDING_DIMENSIONS,
        workflow_unit_of_work=workflow_unit_of_work,
        frontend_event_projection_writer=frontend_event_projection_writer,
    )
    return result, workflow_unit_of_work


@pytest.mark.asyncio
async def test_projects_batch_completed_and_generated_events() -> None:
    repository = InMemoryFrontendWorkflowEventRepository()
    projection_writer = ProjectFrontendWorkflowEvent(
        projector=KnowledgeExtractionFrontendWorkflowEventProjector(),
        repository=repository,
    )

    result, workflow_unit_of_work = await _execute(
        frontend_event_projection_writer=projection_writer,
    )

    assert result.appended_event_count == 2
    assert [event.event_type for event in workflow_unit_of_work.outbox.events] == [
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_EMBEDDING_BATCH_COMPLETED.value,
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_EMBEDDINGS_GENERATED.value,
    ]
    for event in workflow_unit_of_work.outbox.events:
        assert event.payload["operation_key"] == "generate_draft_claim_embeddings"
        assert event.payload["canonical_phase"] == (
            KnowledgeExtractionCanonicalPhase.DRAFT_CLAIM_EMBEDDING.value
        )

    projections = sorted(
        repository.events.values(),
        key=lambda event: event.source_sequence_number,
    )
    assert [event.projection_type for event in projections] == [
        "workflow_draft_claim_embedding_batch_completed",
        "workflow_draft_claim_embeddings_generated",
    ]
    assert projections[0].source_sequence_number < projections[1].source_sequence_number


@pytest.mark.asyncio
async def test_projects_only_generated_event_when_no_inputs() -> None:
    repository = InMemoryFrontendWorkflowEventRepository()
    projection_writer = ProjectFrontendWorkflowEvent(
        projector=KnowledgeExtractionFrontendWorkflowEventProjector(),
        repository=repository,
    )

    result, workflow_unit_of_work = await _execute(
        observations=(),
        persistence_result=PersistDraftClaimEmbeddingsResult(
            requested_count=0,
            inserted_count=0,
            already_exists_count=0,
        ),
        frontend_event_projection_writer=projection_writer,
    )

    assert result.appended_event_count == 1
    assert workflow_unit_of_work.outbox.events[0].event_type == (
        KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_EMBEDDINGS_GENERATED.value
    )
    assert len(repository.events) == 1
    assert next(iter(repository.events.values())).projection_type == (
        "workflow_draft_claim_embeddings_generated"
    )


@pytest.mark.asyncio
async def test_handler_without_projection_writer_preserves_existing_behavior() -> None:
    result, workflow_unit_of_work = await _execute()

    assert result.appended_event_count == 2
    assert len(workflow_unit_of_work.outbox.events) == 2
    assert workflow_unit_of_work.command_log.pending_commands[0].command_type == (
        KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS.value
    )


def test_embedding_handler_projects_after_each_canonical_outbox_append() -> None:
    source = inspect.getsource(HandleGenerateDraftClaimEmbeddingsCommandHandler.execute)

    batch_append_index = source.index("persisted_batch_event =")
    batch_projection_index = source.index(
        "frontend_event_projection_writer.execute(persisted_batch_event)"
    )
    generated_append_index = source.index("persisted_generated_event =")
    generated_projection_index = source.index(
        "frontend_event_projection_writer.execute(persisted_generated_event)"
    )
    assert batch_append_index < batch_projection_index
    assert generated_append_index < generated_projection_index
    assert batch_projection_index < generated_append_index
