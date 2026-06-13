from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_saga_state import (
    KnowledgeExtractionPhaseKey,
    KnowledgeExtractionWorkflowState,
    KnowledgeExtractionWorkflowStatus,
)
from src.contexts.knowledge_workbench.application.sagas.resume_knowledge_extraction_workflow import (
    ResumeKnowledgeExtractionWorkflow,
    ResumeKnowledgeExtractionWorkflowCommand,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.entities.workflow_timeline_entry import (
    WorkflowTimelineEntry,
)


def _now() -> datetime:
    return datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)


def _state(
    status: KnowledgeExtractionWorkflowStatus,
) -> KnowledgeExtractionWorkflowState:
    return KnowledgeExtractionWorkflowState(
        workflow_run_id="workflow-1",
        project_id="project-1",
        source_document_ref="source-document:project-1:abc",
        status=status,
        current_phase=KnowledgeExtractionPhaseKey.SOURCE_UNITS_CREATED,
        pause_reason="manual_pause"
        if status is KnowledgeExtractionWorkflowStatus.PAUSED
        else None,
        created_at=_now(),
        updated_at=_now(),
    )


@dataclass(slots=True)
class FakeStateRepository:
    state: KnowledgeExtractionWorkflowState | None
    saved_states: list[KnowledgeExtractionWorkflowState] = field(default_factory=list)

    async def load_workflow_state(
        self,
        workflow_run_id: str,
    ) -> KnowledgeExtractionWorkflowState | None:
        assert workflow_run_id == "workflow-1"
        return self.state

    async def save_workflow_state(
        self,
        state: KnowledgeExtractionWorkflowState,
    ) -> None:
        self.state = state
        self.saved_states.append(state)


@dataclass(slots=True)
class FakeOutbox:
    events: list[WorkflowEvent] = field(default_factory=list)

    async def append_event(self, event: WorkflowEvent) -> WorkflowEvent:
        self.events.append(event)
        return event


@dataclass(slots=True)
class FakeTimeline:
    entries: list[WorkflowTimelineEntry] = field(default_factory=list)

    async def append_entry(
        self,
        entry: WorkflowTimelineEntry,
    ) -> WorkflowTimelineEntry:
        self.entries.append(entry)
        return entry


@dataclass(slots=True)
class FakeWorkflowUnitOfWork:
    outbox: FakeOutbox = field(default_factory=FakeOutbox)
    timeline: FakeTimeline = field(default_factory=FakeTimeline)


@pytest.mark.asyncio
async def test_resume_marks_workflow_running_and_appends_event_timeline() -> None:
    repository = FakeStateRepository(
        state=_state(KnowledgeExtractionWorkflowStatus.PAUSED)
    )
    unit_of_work = FakeWorkflowUnitOfWork()

    result = await ResumeKnowledgeExtractionWorkflow(
        state_repository=repository,
        workflow_unit_of_work=unit_of_work,
    ).execute(
        ResumeKnowledgeExtractionWorkflowCommand(
            workflow_run_id="workflow-1",
            project_id="project-1",
            actor_user_id="owner-1",
            occurred_at=_now(),
        )
    )

    assert result.status == "running"
    assert result.already_running is False
    assert repository.state is not None
    assert repository.state.status is KnowledgeExtractionWorkflowStatus.RUNNING
    assert repository.state.pause_reason is None
    assert len(unit_of_work.outbox.events) == 1
    assert unit_of_work.outbox.events[0].event_type == "WorkflowManuallyResumed"
    assert len(unit_of_work.timeline.entries) == 1


@pytest.mark.asyncio
async def test_resume_is_idempotent_if_already_running() -> None:
    repository = FakeStateRepository(
        state=_state(KnowledgeExtractionWorkflowStatus.RUNNING)
    )
    unit_of_work = FakeWorkflowUnitOfWork()

    result = await ResumeKnowledgeExtractionWorkflow(
        state_repository=repository,
        workflow_unit_of_work=unit_of_work,
    ).execute(
        ResumeKnowledgeExtractionWorkflowCommand(
            workflow_run_id="workflow-1",
            project_id="project-1",
            actor_user_id="owner-1",
            occurred_at=_now(),
        )
    )

    assert result.already_running is True
    assert repository.saved_states == []
    assert unit_of_work.outbox.events == []
    assert unit_of_work.timeline.entries == []
