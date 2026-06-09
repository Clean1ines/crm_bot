from dataclasses import dataclass
from datetime import datetime

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_ports import (
    KnowledgeExtractionCommandEmitterPort,
    KnowledgeExtractionCommandLogPort,
    KnowledgeExtractionEventCursorPort,
    KnowledgeExtractionSagaStateRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionPhaseCheckpoint,
    KnowledgeExtractionPhaseKey,
    KnowledgeExtractionWorkflowState,
    KnowledgeExtractionWorkflowStatus,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_source_phase_reconciliation import (
    KnowledgeExtractionSourcePhaseReconciler,
)


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
    ) -> None:
        self._state_repository = state_repository
        self._command_log = command_log
        self._event_cursor = event_cursor
        self._command_emitter = command_emitter
        self._source_phase_reconciler = source_phase_reconciler

    async def reconcile(
        self,
        command: ReconcileKnowledgeExtractionSagaCommand,
    ) -> ReconcileKnowledgeExtractionSagaResult:
        state = await self._state_repository.load_workflow_state(
            command.workflow_run_id,
        )
        if state is None:
            raise ValueError("knowledge extraction workflow state not found")

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
