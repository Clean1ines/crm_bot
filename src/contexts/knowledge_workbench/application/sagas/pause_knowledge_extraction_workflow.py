from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_ports import (
    KnowledgeExtractionSagaStateRepositoryPort,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionWorkflowState,
    KnowledgeExtractionWorkflowStatus,
)
from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalEventType,
    KnowledgeExtractionCanonicalPhase,
)
from src.contexts.workflow_runtime.application.ports.workflow_runtime_unit_of_work_port import (
    WorkflowRuntimeUnitOfWorkPort,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.entities.workflow_timeline_entry import (
    WorkflowTimelineEntry,
    WorkflowTimelineSeverity,
)
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)


class KnowledgeExtractionWorkflowPauseNotFoundError(LookupError):
    pass


class KnowledgeExtractionWorkflowPauseProjectMismatchError(PermissionError):
    pass


class KnowledgeExtractionWorkflowPauseTerminalStateError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class PauseKnowledgeExtractionWorkflowCommand:
    workflow_run_id: str
    project_id: str
    actor_user_id: str
    occurred_at: datetime
    reason: str = "manual_pause"

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        _require_non_empty_text(self.project_id, field_name="project_id")
        _require_non_empty_text(self.actor_user_id, field_name="actor_user_id")
        _require_non_empty_text(self.reason, field_name="reason")
        _require_timezone_aware(self.occurred_at, field_name="occurred_at")


@dataclass(frozen=True, slots=True)
class PauseKnowledgeExtractionWorkflowResult:
    workflow_run_id: str
    status: str
    paused_at: datetime
    already_paused: bool

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        _require_non_empty_text(self.status, field_name="status")
        _require_timezone_aware(self.paused_at, field_name="paused_at")
        if not isinstance(self.already_paused, bool):
            raise TypeError("already_paused must be bool")


@dataclass(frozen=True, slots=True)
class PauseKnowledgeExtractionWorkflow:
    state_repository: KnowledgeExtractionSagaStateRepositoryPort
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort

    async def execute(
        self,
        command: PauseKnowledgeExtractionWorkflowCommand,
    ) -> PauseKnowledgeExtractionWorkflowResult:
        state = await self.state_repository.load_workflow_state(command.workflow_run_id)
        if state is None:
            raise KnowledgeExtractionWorkflowPauseNotFoundError(
                "knowledge extraction workflow not found",
            )
        if state.project_id != command.project_id:
            raise KnowledgeExtractionWorkflowPauseProjectMismatchError(
                "workflow does not belong to project",
            )
        if _is_terminal(state):
            raise KnowledgeExtractionWorkflowPauseTerminalStateError(
                "terminal knowledge extraction workflow cannot be paused",
            )
        if state.status is KnowledgeExtractionWorkflowStatus.PAUSED:
            return PauseKnowledgeExtractionWorkflowResult(
                workflow_run_id=state.workflow_run_id,
                status="manually_paused",
                paused_at=state.updated_at or command.occurred_at,
                already_paused=True,
            )

        paused_state = replace(
            state,
            status=KnowledgeExtractionWorkflowStatus.PAUSED,
            pause_reason=command.reason,
            updated_at=command.occurred_at,
        )
        await self.state_repository.save_workflow_state(paused_state)
        await self.workflow_unit_of_work.outbox.append_event(
            _workflow_event(
                state=paused_state,
                actor_user_id=command.actor_user_id,
                event_type=(
                    KnowledgeExtractionCanonicalEventType.WORKFLOW_MANUALLY_PAUSED.value
                ),
                reason=command.reason,
                occurred_at=command.occurred_at,
            )
        )
        await self.workflow_unit_of_work.timeline.append_entry(
            _timeline_entry(
                state=paused_state,
                actor_user_id=command.actor_user_id,
                event_type=(
                    KnowledgeExtractionCanonicalEventType.WORKFLOW_MANUALLY_PAUSED.value
                ),
                reason=command.reason,
                occurred_at=command.occurred_at,
                message="Knowledge extraction workflow manually paused",
            )
        )

        return PauseKnowledgeExtractionWorkflowResult(
            workflow_run_id=paused_state.workflow_run_id,
            status="manually_paused",
            paused_at=command.occurred_at,
            already_paused=False,
        )


def _is_terminal(state: KnowledgeExtractionWorkflowState) -> bool:
    return state.status in {
        KnowledgeExtractionWorkflowStatus.COMPLETED,
        KnowledgeExtractionWorkflowStatus.FAILED,
        KnowledgeExtractionWorkflowStatus.CANCELLED,
    }


def _workflow_event(
    *,
    state: KnowledgeExtractionWorkflowState,
    actor_user_id: str,
    event_type: str,
    reason: str,
    occurred_at: datetime,
) -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId(
            f"workflow-event:{state.workflow_run_id}:{event_type}:{_stamp(occurred_at)}"
        ),
        event_type=event_type,
        workflow_run_id=state.workflow_run_id,
        payload={
            "workflow_run_id": state.workflow_run_id,
            "project_id": state.project_id,
            "source_document_ref": state.source_document_ref,
            "actor_user_id": actor_user_id,
            "reason": reason,
        },
        occurred_at=occurred_at,
        correlation_id=state.workflow_run_id,
    )


def _timeline_entry(
    *,
    state: KnowledgeExtractionWorkflowState,
    actor_user_id: str,
    event_type: str,
    reason: str,
    occurred_at: datetime,
    message: str,
) -> WorkflowTimelineEntry:
    return WorkflowTimelineEntry(
        timeline_entry_id=(
            f"workflow-timeline:{state.workflow_run_id}:{event_type}:"
            f"{_stamp(occurred_at)}"
        ),
        workflow_run_id=state.workflow_run_id,
        event_type=event_type,
        phase=KnowledgeExtractionCanonicalPhase.CLAIM_BUILDER_SECTION_EXTRACTION.value,
        severity=WorkflowTimelineSeverity.INFO,
        message=message,
        payload_summary={
            "workflow_run_id": state.workflow_run_id,
            "project_id": state.project_id,
            "source_document_ref": state.source_document_ref,
            "actor_user_id": actor_user_id,
            "reason": reason,
        },
        occurred_at=occurred_at,
        source_ref=state.source_document_ref,
    )


def _stamp(value: datetime) -> str:
    return value.isoformat().replace("+00:00", "Z")


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_timezone_aware(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
