from dataclasses import dataclass
from datetime import datetime

from src.contexts.knowledge_workbench.application.sagas.advance_to_draft_observation_scheduling_phase import (
    AdvanceToDraftObservationSchedulingPhase,
    AdvanceToDraftObservationSchedulingPhaseCommand,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_ports import (
    KnowledgeExtractionCommandEmitterPort,
    KnowledgeExtractionCommandLogPort,
    KnowledgeExtractionEventCursorPort,
    KnowledgeExtractionSagaStateRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_source_checkpoint_reconciliation import (
    source_reconciliation_checkpoints,
    state_with_source_reconciliation,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionPhaseKey,
    KnowledgeExtractionWorkflowStatus,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_source_phase_reconciliation import (
    KnowledgeExtractionSourcePhaseReconciler,
)
from src.contexts.knowledge_workbench.source_management.application.ports.source_management_repository_port import (
    SourceManagementRepositoryPort,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)

_SOURCE_DOCUMENT_MISSING_PAUSE_REASON = "source_document_missing"
_SOURCE_UNITS_MISSING_PAUSE_REASON = "source_units_missing"


@dataclass(frozen=True, slots=True)
class ReconcileKnowledgeExtractionSagaCommand:
    workflow_run_id: str
    occurred_at: datetime

    def __post_init__(self) -> None:
        _require_non_empty(self.workflow_run_id, "workflow_run_id")
        _require_timezone_aware(self.occurred_at, "occurred_at")


@dataclass(frozen=True, slots=True)
class ReconcileKnowledgeExtractionSagaResult:
    workflow_run_id: str
    status: KnowledgeExtractionWorkflowStatus
    current_phase: KnowledgeExtractionPhaseKey
    emitted_command_count: int = 0

    def __post_init__(self) -> None:
        _require_non_empty(self.workflow_run_id, "workflow_run_id")
        if self.emitted_command_count < 0:
            raise ValueError("emitted_command_count must be >= 0")


class KnowledgeExtractionSaga:
    """Application contract skeleton for the knowledge extraction workflow.

    This skeleton is not the production orchestrator yet. It exists to fix the
    application contract before durable persistence, event handling, and
    phase-specific reconciliation are implemented.
    """

    def __init__(
        self,
        *,
        state_repository: KnowledgeExtractionSagaStateRepositoryPort,
        command_log: KnowledgeExtractionCommandLogPort,
        event_cursor: KnowledgeExtractionEventCursorPort,
        command_emitter: KnowledgeExtractionCommandEmitterPort,
        source_phase_reconciler: KnowledgeExtractionSourcePhaseReconciler | None = None,
        source_management_repository: SourceManagementRepositoryPort | None = None,
        draft_observation_scheduling_phase: (
            AdvanceToDraftObservationSchedulingPhase | None
        ) = None,
    ) -> None:
        self._state_repository = state_repository
        self._command_log = command_log
        self._event_cursor = event_cursor
        self._command_emitter = command_emitter
        self._source_phase_reconciler = source_phase_reconciler
        self._source_management_repository = source_management_repository
        self._draft_observation_scheduling_phase = draft_observation_scheduling_phase

    async def reconcile(
        self,
        command: ReconcileKnowledgeExtractionSagaCommand,
    ) -> ReconcileKnowledgeExtractionSagaResult:
        state = await self._state_repository.load_workflow_state(
            command.workflow_run_id,
        )
        if state is None:
            raise ValueError("knowledge extraction workflow state not found")
        if self._source_phase_reconciler is not None:
            source_result = await self._source_phase_reconciler.reconcile_source_phases(
                state,
            )
            checkpoints = source_reconciliation_checkpoints(
                state,
                source_result,
                command.occurred_at,
            )
            for checkpoint in checkpoints:
                await self._state_repository.save_phase_checkpoint(checkpoint)
            next_state = state_with_source_reconciliation(
                state,
                source_result,
                checkpoints,
                command.occurred_at,
            )
            if next_state != state:
                await self._state_repository.save_workflow_state(next_state)
                state = next_state

        if (
            self._source_management_repository is not None
            and self._draft_observation_scheduling_phase is not None
            and state.status is KnowledgeExtractionWorkflowStatus.RUNNING
            and state.current_phase is KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED
        ):
            source_units = (
                await self._source_management_repository.list_source_units_for_document(
                    SourceDocumentRef(state.source_document_ref),
                )
            )
            phase_result = self._draft_observation_scheduling_phase.execute(
                AdvanceToDraftObservationSchedulingPhaseCommand(
                    state=state,
                    source_units=source_units,
                    occurred_at=command.occurred_at,
                ),
            )
            if (
                phase_result.state.current_phase
                is not KnowledgeExtractionPhaseKey.PROMPT_A_WORK_SCHEDULED
            ):
                raise ValueError("draft observation scheduling phase did not advance")
            await self._state_repository.save_phase_checkpoint(phase_result.checkpoint)
            if phase_result.state != state:
                await self._state_repository.save_workflow_state(phase_result.state)
                state = phase_result.state

        return ReconcileKnowledgeExtractionSagaResult(
            workflow_run_id=state.workflow_run_id,
            status=state.status,
            current_phase=state.current_phase,
            emitted_command_count=0,
        )


def _require_non_empty(value: str, field_name: str) -> None:
    if not value or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
