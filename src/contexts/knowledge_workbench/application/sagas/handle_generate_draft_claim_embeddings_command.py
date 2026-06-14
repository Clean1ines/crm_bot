from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256

from src.contexts.embedding_runtime.application.ports.embedding_generation_port import (
    EmbeddingGenerationPort,
    EmbeddingGenerationRequest,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalCommandType,
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.extraction.application.policies.draft_claim_embedding_input_builder import (
    DraftClaimEmbeddingInput,
    DraftClaimEmbeddingInputBuilder,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_embedding_persistence_port import (
    DraftClaimEmbeddingCandidate,
    DraftClaimEmbeddingPersistencePort,
    PersistDraftClaimEmbeddingsResult,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_embedding_read_repository_port import (
    DraftClaimEmbeddingReadRepositoryPort,
)
from src.contexts.workflow_runtime.application.ports.workflow_runtime_unit_of_work_port import (
    WorkflowRuntimeUnitOfWorkPort,
)
from src.contexts.workflow_runtime.domain.entities.workflow_command import (
    WorkflowCommand,
    WorkflowCommandStatus,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.entities.workflow_progress_snapshot import (
    WorkflowProgressSnapshot,
)
from src.contexts.workflow_runtime.domain.entities.workflow_timeline_entry import (
    WorkflowTimelineEntry,
    WorkflowTimelineSeverity,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_command_id import (
    WorkflowCommandId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_idempotency_key import (
    WorkflowIdempotencyKey,
)


@dataclass(frozen=True, slots=True)
class HandleGenerateDraftClaimEmbeddingsCommand:
    workflow_command: WorkflowCommand

    def __post_init__(self) -> None:
        if not isinstance(self.workflow_command, WorkflowCommand):
            raise TypeError("workflow_command must be WorkflowCommand")


@dataclass(frozen=True, slots=True)
class HandleGenerateDraftClaimEmbeddingsResult:
    workflow_run_id: str
    requested_embedding_count: int
    persisted_embedding_count: int
    appended_event_count: int
    appended_next_command_count: int
    completed_command_id: WorkflowCommandId

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, "workflow_run_id")
        _require_non_negative_int(
            self.requested_embedding_count,
            "requested_embedding_count",
        )
        _require_non_negative_int(
            self.persisted_embedding_count,
            "persisted_embedding_count",
        )
        _require_non_negative_int(self.appended_event_count, "appended_event_count")
        _require_non_negative_int(
            self.appended_next_command_count,
            "appended_next_command_count",
        )
        if not isinstance(self.completed_command_id, WorkflowCommandId):
            raise TypeError("completed_command_id must be WorkflowCommandId")


class HandleGenerateDraftClaimEmbeddingsCommandHandler:
    def __init__(
        self,
        *,
        input_builder: DraftClaimEmbeddingInputBuilder | None = None,
        read_limit: int = 1000,
    ) -> None:
        if read_limit <= 0:
            raise ValueError("read_limit must be > 0")
        self._input_builder = input_builder or DraftClaimEmbeddingInputBuilder()
        self._read_limit = read_limit

    async def execute(
        self,
        command: HandleGenerateDraftClaimEmbeddingsCommand,
        *,
        draft_claim_embedding_read_repository: DraftClaimEmbeddingReadRepositoryPort,
        draft_claim_embedding_persistence: DraftClaimEmbeddingPersistencePort,
        embedding_generation_port: EmbeddingGenerationPort,
        embedding_model_id: str,
        embedding_dimensions: int,
        workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    ) -> HandleGenerateDraftClaimEmbeddingsResult:
        workflow_command = command.workflow_command
        _validate_workflow_command(workflow_command)
        _require_non_empty_text(embedding_model_id, "embedding_model_id")
        if embedding_dimensions <= 0:
            raise ValueError("embedding_dimensions must be positive")

        workflow_run_id = _payload_text(
            workflow_command.payload,
            "workflow_run_id",
            fallback=workflow_command.workflow_run_id,
        )
        if workflow_run_id != workflow_command.workflow_run_id:
            raise ValueError("payload workflow_run_id must match workflow command")

        occurred_at = workflow_command.updated_at
        observations = await draft_claim_embedding_read_repository.list_unembedded_claim_observations_by_workflow_run_id(
            workflow_run_id=workflow_run_id,
            embedding_model_id=embedding_model_id,
            limit=self._read_limit,
        )
        inputs = self._input_builder.build(observations)

        persistence_result = PersistDraftClaimEmbeddingsResult(
            requested_count=0,
            inserted_count=0,
            already_exists_count=0,
        )
        if inputs:
            embedding_result = await embedding_generation_port.embed(
                EmbeddingGenerationRequest(
                    texts=tuple(item.text for item in inputs),
                    model_id=embedding_model_id,
                    expected_dimensions=embedding_dimensions,
                    task="retrieval.passage",
                )
            )
            if len(embedding_result.embeddings) != len(inputs):
                raise ValueError("embedding result count must match input count")
            if embedding_result.dimensions != embedding_dimensions:
                raise ValueError(
                    "embedding result dimensions must match expected dimensions"
                )

            persistence_result = (
                await draft_claim_embedding_persistence.persist_draft_claim_embeddings(
                    _candidates(
                        workflow_command=workflow_command,
                        workflow_run_id=workflow_run_id,
                        inputs=inputs,
                        vectors=embedding_result.embeddings,
                        embedding_model_id=embedding_model_id,
                        dimensions=embedding_dimensions,
                    )
                )
            )

            await workflow_unit_of_work.outbox.append_event(
                _batch_completed_event(
                    workflow_command=workflow_command,
                    workflow_run_id=workflow_run_id,
                    persistence_result=persistence_result,
                    embedding_model_id=embedding_model_id,
                    dimensions=embedding_dimensions,
                )
            )

        await workflow_unit_of_work.outbox.append_event(
            _generated_event(
                workflow_command=workflow_command,
                workflow_run_id=workflow_run_id,
                persistence_result=persistence_result,
                embedding_model_id=embedding_model_id,
                dimensions=embedding_dimensions,
            )
        )

        next_command = _cluster_draft_claims_command(
            workflow_command=workflow_command,
            workflow_run_id=workflow_run_id,
        )
        await workflow_unit_of_work.command_log.append_pending_command(next_command)

        await _save_progress_snapshot(
            workflow_unit_of_work=workflow_unit_of_work,
            workflow_run_id=workflow_run_id,
            persistence_result=persistence_result,
            occurred_at=occurred_at,
        )
        await workflow_unit_of_work.timeline.append_entry(
            _timeline_entry(
                workflow_command=workflow_command,
                workflow_run_id=workflow_run_id,
                persistence_result=persistence_result,
                occurred_at=occurred_at,
            )
        )
        await workflow_unit_of_work.command_log.mark_command_completed(
            command_id=workflow_command.command_id,
            completed_at=occurred_at,
        )

        return HandleGenerateDraftClaimEmbeddingsResult(
            workflow_run_id=workflow_run_id,
            requested_embedding_count=persistence_result.requested_count,
            persisted_embedding_count=persistence_result.inserted_count,
            appended_event_count=2 if inputs else 1,
            appended_next_command_count=1,
            completed_command_id=workflow_command.command_id,
        )


def _validate_workflow_command(workflow_command: WorkflowCommand) -> None:
    if (
        workflow_command.command_type
        != KnowledgeExtractionCanonicalCommandType.GENERATE_DRAFT_CLAIM_EMBEDDINGS.value
    ):
        raise ValueError(
            "workflow_command command_type must be GenerateDraftClaimEmbeddings"
        )
    if workflow_command.status is not WorkflowCommandStatus.PENDING:
        raise ValueError("workflow_command status must be PENDING")


def _candidates(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    inputs: tuple[DraftClaimEmbeddingInput, ...],
    vectors: tuple[tuple[float, ...], ...],
    embedding_model_id: str,
    dimensions: int,
) -> tuple[DraftClaimEmbeddingCandidate, ...]:
    source_document_ref = _payload_text(workflow_command.payload, "source_document_ref")
    return tuple(
        DraftClaimEmbeddingCandidate(
            workflow_run_id=workflow_run_id,
            source_document_ref=source_document_ref,
            source_unit_ref=item.source_unit_ref.value,
            observation_ref=item.observation_ref.value,
            embedding_text=item.text,
            embedding_text_hash=_text_hash(item.text),
            embedding_model_id=embedding_model_id,
            dimensions=dimensions,
            vector=tuple(float(value) for value in vector),
            created_at=workflow_command.updated_at,
        )
        for item, vector in zip(inputs, vectors, strict=True)
    )


def _text_hash(text: str) -> str:
    return sha256(text.encode("utf-8")).hexdigest()


def _cluster_draft_claims_command(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
) -> WorkflowCommand:
    idempotency_key = f"cluster-draft-claims:{workflow_run_id}"
    return WorkflowCommand(
        command_id=WorkflowCommandId(f"workflow-command:{idempotency_key}"),
        command_type=KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS.value,
        workflow_run_id=workflow_run_id,
        idempotency_key=WorkflowIdempotencyKey(idempotency_key),
        payload={"workflow_run_id": workflow_run_id},
        status=WorkflowCommandStatus.PENDING,
        run_after=workflow_command.updated_at,
        created_at=workflow_command.updated_at,
        updated_at=workflow_command.updated_at,
        correlation_id=workflow_command.command_id.value,
    )


def _batch_completed_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    persistence_result: PersistDraftClaimEmbeddingsResult,
    embedding_model_id: str,
    dimensions: int,
) -> WorkflowEvent:
    return _event(
        workflow_command=workflow_command,
        workflow_run_id=workflow_run_id,
        event_type=KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_EMBEDDING_BATCH_COMPLETED,
        suffix="batch-completed",
        payload=_payload(
            workflow_run_id=workflow_run_id,
            persistence_result=persistence_result,
            embedding_model_id=embedding_model_id,
            dimensions=dimensions,
        ),
    )


def _generated_event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    persistence_result: PersistDraftClaimEmbeddingsResult,
    embedding_model_id: str,
    dimensions: int,
) -> WorkflowEvent:
    return _event(
        workflow_command=workflow_command,
        workflow_run_id=workflow_run_id,
        event_type=KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_EMBEDDINGS_GENERATED,
        suffix="generated",
        payload=_payload(
            workflow_run_id=workflow_run_id,
            persistence_result=persistence_result,
            embedding_model_id=embedding_model_id,
            dimensions=dimensions,
        ),
    )


def _event(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    event_type: KnowledgeExtractionCanonicalEventType,
    suffix: str,
    payload: Mapping[str, object],
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            f"workflow-event:{workflow_run_id}:{event_type.value}:"
            f"{workflow_command.command_id.value}:{suffix}"
        ),
        event_type=event_type.value,
        workflow_run_id=workflow_run_id,
        payload=payload,
        occurred_at=workflow_command.updated_at,
        causation_command_id=workflow_command.command_id,
        correlation_id=workflow_command.command_id.value,
    )


def _payload(
    *,
    workflow_run_id: str,
    persistence_result: PersistDraftClaimEmbeddingsResult,
    embedding_model_id: str,
    dimensions: int,
) -> dict[str, object]:
    return {
        "workflow_run_id": workflow_run_id,
        "requested_count": persistence_result.requested_count,
        "persisted_count": persistence_result.inserted_count,
        "already_exists_count": persistence_result.already_exists_count,
        "embedding_model_id": embedding_model_id,
        "dimensions": dimensions,
    }


async def _save_progress_snapshot(
    *,
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort,
    workflow_run_id: str,
    persistence_result: PersistDraftClaimEmbeddingsResult,
    occurred_at,
) -> None:
    existing = await workflow_unit_of_work.progress_snapshots.get_snapshot(
        workflow_run_id,
    )
    domain_counters = dict(existing.domain_counters) if existing is not None else {}
    domain_counters["draft_claim_embedding_requested_count"] = (
        persistence_result.requested_count
    )
    domain_counters["draft_claim_embedding_persisted_count"] = (
        persistence_result.inserted_count
    )
    domain_counters["draft_claim_embedding_already_exists_count"] = (
        persistence_result.already_exists_count
    )
    await workflow_unit_of_work.progress_snapshots.save_snapshot(
        WorkflowProgressSnapshot(
            workflow_run_id=workflow_run_id,
            current_phase="DRAFT_CLAIM_EMBEDDING",
            workflow_status="RUNNING",
            total_work_items=existing.total_work_items if existing is not None else 0,
            scheduled_work_items=(
                existing.scheduled_work_items if existing is not None else 0
            ),
            running_work_items=0,
            completed_work_items=(
                existing.completed_work_items if existing is not None else 0
            ),
            deferred_work_items=existing.deferred_work_items
            if existing is not None
            else 0,
            retryable_failed_work_items=(
                existing.retryable_failed_work_items if existing is not None else 0
            ),
            terminal_failed_work_items=(
                existing.terminal_failed_work_items if existing is not None else 0
            ),
            blocked_work_items=0,
            domain_counters=domain_counters,
            started_at=existing.started_at if existing is not None else occurred_at,
            updated_at=occurred_at,
            completed_at=existing.completed_at if existing is not None else None,
        ),
    )


def _timeline_entry(
    *,
    workflow_command: WorkflowCommand,
    workflow_run_id: str,
    persistence_result: PersistDraftClaimEmbeddingsResult,
    occurred_at,
) -> WorkflowTimelineEntry:
    return WorkflowTimelineEntry(
        timeline_entry_id=(
            f"workflow-timeline:{workflow_run_id}:"
            f"DraftClaimEmbeddingsGenerated:{workflow_command.command_id.value}"
        ),
        workflow_run_id=workflow_run_id,
        event_type=KnowledgeExtractionCanonicalEventType.DRAFT_CLAIM_EMBEDDINGS_GENERATED.value,
        phase="DRAFT_CLAIM_EMBEDDING",
        severity=WorkflowTimelineSeverity.INFO,
        message="Draft claim embeddings generated",
        payload_summary={
            "workflow_run_id": workflow_run_id,
            "requested_count": persistence_result.requested_count,
            "persisted_count": persistence_result.inserted_count,
            "already_exists_count": persistence_result.already_exists_count,
            "next_command_type": KnowledgeExtractionCanonicalCommandType.CLUSTER_DRAFT_CLAIMS.value,
        },
        occurred_at=occurred_at,
        source_ref=workflow_command.command_type,
    )


def _payload_text(
    payload: Mapping[str, object],
    key: str,
    *,
    fallback: str | None = None,
) -> str:
    value = payload.get(key, fallback)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"workflow command payload must include {key}")
    return value


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")
