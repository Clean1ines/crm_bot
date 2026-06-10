from dataclasses import dataclass
from typing import Protocol

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionPhaseCheckpoint,
    KnowledgeExtractionPhaseKey,
    KnowledgeExtractionPhaseStatus,
    KnowledgeExtractionWorkflowState,
    KnowledgeExtractionWorkflowStatus,
)
from src.contexts.knowledge_workbench.application.sagas.start_source_ingestion_workflow import (
    SourceIngestionAcceptedPlan,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_document import (
    SourceDocument,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)


class PersistAcceptedSourceIngestionPlanSourceDocumentPort(Protocol):
    async def save_source_document(self, document: SourceDocument) -> None: ...


class PersistAcceptedSourceIngestionPlanSagaStatePort(Protocol):
    async def save_workflow_state(
        self,
        state: KnowledgeExtractionWorkflowState,
    ) -> None: ...

    async def save_phase_checkpoint(
        self,
        checkpoint: KnowledgeExtractionPhaseCheckpoint,
    ) -> None: ...


class PersistAcceptedSourceIngestionPlanUnitOfWorkPort(Protocol):
    source_management: PersistAcceptedSourceIngestionPlanSourceDocumentPort
    saga_state: PersistAcceptedSourceIngestionPlanSagaStatePort

    async def commit(self) -> None: ...

    async def rollback(self) -> None: ...


@dataclass(frozen=True, slots=True)
class PersistAcceptedSourceIngestionPlanCommand:
    accepted_plan: SourceIngestionAcceptedPlan

    def __post_init__(self) -> None:
        if not isinstance(self.accepted_plan, SourceIngestionAcceptedPlan):
            raise TypeError("accepted_plan must be SourceIngestionAcceptedPlan")


@dataclass(frozen=True, slots=True)
class PersistAcceptedSourceIngestionPlanResult:
    workflow_run_id: str
    source_document_ref: str
    document_checkpoint_status: KnowledgeExtractionPhaseStatus
    source_document_persisted: bool

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        _require_non_empty_text(
            self.source_document_ref,
            field_name="source_document_ref",
        )
        if not isinstance(
            self.document_checkpoint_status,
            KnowledgeExtractionPhaseStatus,
        ):
            raise TypeError(
                "document_checkpoint_status must be KnowledgeExtractionPhaseStatus",
            )


class PersistAcceptedSourceIngestionPlan:
    def __init__(
        self,
        *,
        unit_of_work: PersistAcceptedSourceIngestionPlanUnitOfWorkPort,
    ) -> None:
        self._unit_of_work = unit_of_work

    async def execute(
        self,
        command: PersistAcceptedSourceIngestionPlanCommand,
    ) -> PersistAcceptedSourceIngestionPlanResult:
        accepted_plan = command.accepted_plan
        source_document_ref = SourceDocumentRef(accepted_plan.source_document_ref)
        workflow_run_id = _build_workflow_run_id(
            source_document_ref=accepted_plan.source_document_ref,
        )

        document = SourceDocument(
            document_ref=source_document_ref,
            project_id=accepted_plan.project_id,
            source_format=accepted_plan.source_format,
            content_hash=accepted_plan.content_hash,
            original_filename=accepted_plan.original_filename,
            created_at=accepted_plan.occurred_at,
        )

        document_accepted = _build_document_accepted_checkpoint(
            workflow_run_id=workflow_run_id,
            accepted_plan=accepted_plan,
        )
        source_document_persisted = _build_source_document_persisted_checkpoint(
            workflow_run_id=workflow_run_id,
            accepted_plan=accepted_plan,
        )

        state = KnowledgeExtractionWorkflowState(
            workflow_run_id=workflow_run_id,
            project_id=accepted_plan.project_id,
            source_document_ref=accepted_plan.source_document_ref,
            status=KnowledgeExtractionWorkflowStatus.RUNNING,
            current_phase=KnowledgeExtractionPhaseKey.SOURCE_DOCUMENT_PERSISTED,
            checkpoints=(document_accepted, source_document_persisted),
            created_at=accepted_plan.occurred_at,
            updated_at=accepted_plan.occurred_at,
        )

        try:
            await self._unit_of_work.source_management.save_source_document(document)
            await self._unit_of_work.saga_state.save_workflow_state(state)
            await self._unit_of_work.saga_state.save_phase_checkpoint(
                document_accepted,
            )
            await self._unit_of_work.saga_state.save_phase_checkpoint(
                source_document_persisted,
            )
            await self._unit_of_work.commit()
        except Exception:
            await self._unit_of_work.rollback()
            raise

        return PersistAcceptedSourceIngestionPlanResult(
            workflow_run_id=workflow_run_id,
            source_document_ref=accepted_plan.source_document_ref,
            document_checkpoint_status=source_document_persisted.phase_status,
            source_document_persisted=True,
        )


def _build_workflow_run_id(*, source_document_ref: str) -> str:
    return f"knowledge-extraction:{source_document_ref}"


def _build_document_accepted_checkpoint(
    *,
    workflow_run_id: str,
    accepted_plan: SourceIngestionAcceptedPlan,
) -> KnowledgeExtractionPhaseCheckpoint:
    return KnowledgeExtractionPhaseCheckpoint(
        workflow_run_id=workflow_run_id,
        phase_key=KnowledgeExtractionPhaseKey.DOCUMENT_ACCEPTED,
        phase_status=KnowledgeExtractionPhaseStatus.COMPLETED,
        expected_count=1,
        completed_count=1,
        failed_count=0,
        blocked_count=0,
        idempotency_key=f"document-accepted:{accepted_plan.source_document_ref}",
        checkpoint_payload={
            "project_id": accepted_plan.project_id,
            "source_document_ref": accepted_plan.source_document_ref,
            "actor_user_id": accepted_plan.actor_user_id,
            "original_filename": accepted_plan.original_filename,
            "source_format": accepted_plan.source_format.value,
            "content_hash": accepted_plan.content_hash,
        },
        updated_at=accepted_plan.occurred_at,
    )


def _build_source_document_persisted_checkpoint(
    *,
    workflow_run_id: str,
    accepted_plan: SourceIngestionAcceptedPlan,
) -> KnowledgeExtractionPhaseCheckpoint:
    return KnowledgeExtractionPhaseCheckpoint(
        workflow_run_id=workflow_run_id,
        phase_key=KnowledgeExtractionPhaseKey.SOURCE_DOCUMENT_PERSISTED,
        phase_status=KnowledgeExtractionPhaseStatus.COMPLETED,
        expected_count=1,
        completed_count=1,
        failed_count=0,
        blocked_count=0,
        idempotency_key=(
            f"source-document-persisted:{accepted_plan.source_document_ref}"
        ),
        checkpoint_payload={
            "source_document_ref": accepted_plan.source_document_ref,
            "content_hash": accepted_plan.content_hash,
        },
        updated_at=accepted_plan.occurred_at,
    )


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
