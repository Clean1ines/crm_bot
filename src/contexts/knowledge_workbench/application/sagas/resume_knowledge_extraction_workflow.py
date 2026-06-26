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
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
)


class KnowledgeExtractionWorkflowResumeStateNotFoundError(LookupError):
    pass


class KnowledgeExtractionWorkflowResumeProjectMismatchError(PermissionError):
    pass


class KnowledgeExtractionWorkflowResumeTerminalStateError(ValueError):
    pass


class KnowledgeExtractionWorkflowResumeNotPausedError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ResumeKnowledgeExtractionWorkflowCommand:
    workflow_run_id: str
    project_id: str
    actor_user_id: str
    occurred_at: datetime
    max_drain_commands: int = 10

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        _require_non_empty_text(self.project_id, field_name="project_id")
        _require_non_empty_text(self.actor_user_id, field_name="actor_user_id")
        _require_timezone_aware(self.occurred_at, field_name="occurred_at")
        if not isinstance(self.max_drain_commands, int):
            raise TypeError("max_drain_commands must be int")
        if self.max_drain_commands <= 0:
            raise ValueError("max_drain_commands must be > 0")


@dataclass(frozen=True, slots=True)
class ResumeKnowledgeExtractionWorkflowResult:
    workflow_run_id: str
    status: str
    resumed_at: datetime
    already_running: bool

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        _require_non_empty_text(self.status, field_name="status")
        _require_timezone_aware(self.resumed_at, field_name="resumed_at")
        if not isinstance(self.already_running, bool):
            raise TypeError("already_running must be bool")


@dataclass(frozen=True, slots=True)
class ResumeKnowledgeExtractionWorkflow:
    state_repository: KnowledgeExtractionSagaStateRepositoryPort
    workflow_unit_of_work: WorkflowRuntimeUnitOfWorkPort

    async def execute(
        self,
        command: ResumeKnowledgeExtractionWorkflowCommand,
        *,
        frontend_event_projection_writer: ProjectFrontendWorkflowEvent | None = None,
    ) -> ResumeKnowledgeExtractionWorkflowResult:
        state = await self.state_repository.load_workflow_state(command.workflow_run_id)
        if state is None:
            raise KnowledgeExtractionWorkflowResumeStateNotFoundError(
                "knowledge extraction workflow not found",
            )
        if state.project_id != command.project_id:
            raise KnowledgeExtractionWorkflowResumeProjectMismatchError(
                "workflow does not belong to project",
            )
        if _is_terminal(state):
            raise KnowledgeExtractionWorkflowResumeTerminalStateError(
                "terminal knowledge extraction workflow cannot be resumed",
            )
        if state.status is KnowledgeExtractionWorkflowStatus.RUNNING:
            return ResumeKnowledgeExtractionWorkflowResult(
                workflow_run_id=state.workflow_run_id,
                status="running",
                resumed_at=state.updated_at or command.occurred_at,
                already_running=True,
            )
        if state.status is not KnowledgeExtractionWorkflowStatus.PAUSED:
            raise KnowledgeExtractionWorkflowResumeNotPausedError(
                "knowledge extraction workflow is not manually paused",
            )

        resumed_state = replace(
            state,
            status=KnowledgeExtractionWorkflowStatus.RUNNING,
            pause_reason=None,
            updated_at=command.occurred_at,
        )
        await self.state_repository.save_workflow_state(resumed_state)
        resumed_event = await self.workflow_unit_of_work.outbox.append_event(
            _workflow_event(
                state=resumed_state,
                actor_user_id=command.actor_user_id,
                event_type=(
                    KnowledgeExtractionCanonicalEventType.WORKFLOW_MANUALLY_RESUMED.value
                ),
                occurred_at=command.occurred_at,
            )
        )
        if frontend_event_projection_writer is not None:
            await frontend_event_projection_writer.execute(resumed_event)
        await self.workflow_unit_of_work.timeline.append_entry(
            _timeline_entry(
                state=resumed_state,
                actor_user_id=command.actor_user_id,
                event_type=(
                    KnowledgeExtractionCanonicalEventType.WORKFLOW_MANUALLY_RESUMED.value
                ),
                occurred_at=command.occurred_at,
                message="Knowledge extraction workflow manually resumed",
            )
        )

        return ResumeKnowledgeExtractionWorkflowResult(
            workflow_run_id=resumed_state.workflow_run_id,
            status="running",
            resumed_at=command.occurred_at,
            already_running=False,
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
            "operation_key": "manual_resume",
            "canonical_phase": KnowledgeExtractionCanonicalPhase.SOURCE_INGESTION.value,
            "actor_user_id": actor_user_id,
        },
        occurred_at=occurred_at,
        correlation_id=state.workflow_run_id,
    )


def _timeline_entry(
    *,
    state: KnowledgeExtractionWorkflowState,
    actor_user_id: str,
    event_type: str,
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
