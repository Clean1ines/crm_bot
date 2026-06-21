from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.application.sagas.knowledge_extraction_workflow_definition import (
    KnowledgeExtractionCanonicalEventType,
)
from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.application.projectors.project_frontend_workflow_event import (
    ProjectFrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.application.projectors.source_ingestion_frontend_workflow_event_projector import (
    SourceIngestionFrontendWorkflowEventProjector,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_event_id import (
    WorkflowEventId,
)


def _now() -> datetime:
    return datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)


def _source_units_created() -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId("source-event-1"),
        event_type=KnowledgeExtractionCanonicalEventType.SOURCE_UNITS_CREATED.value,
        workflow_run_id="workflow-1",
        payload={
            "project_id": "project-1",
            "source_document_ref": "document-1",
            "source_unit_count": 3,
        },
        occurred_at=_now(),
        sequence_number=17,
    )


def _unsupported_event() -> WorkflowEvent:
    return WorkflowEvent(
        event_id=WorkflowEventId("unsupported-event-1"),
        event_type="UnsupportedSourceIngestionEvent",
        workflow_run_id="workflow-1",
        payload={},
        occurred_at=_now(),
        sequence_number=18,
    )


class InMemoryRepository:
    def __init__(self) -> None:
        self.events: dict[str, FrontendWorkflowEvent] = {}

    async def append(self, event: FrontendWorkflowEvent) -> FrontendWorkflowEvent:
        existing = self.events.get(event.projection_event_id)
        if existing is not None:
            return existing
        self.events[event.projection_event_id] = event
        return event


@pytest.mark.asyncio
async def test_projects_and_persists_same_source_event_idempotently() -> None:
    repository = InMemoryRepository()
    use_case = ProjectFrontendWorkflowEvent(
        projector=SourceIngestionFrontendWorkflowEventProjector(),
        repository=repository,
    )

    first = await use_case.execute(_source_units_created())
    second = await use_case.execute(_source_units_created())

    assert first == second
    assert first is not None
    assert tuple(repository.events) == (
        "frontend-workflow-event:source-event-1:workflow_source_units_created:v1",
    )


@pytest.mark.asyncio
async def test_unsupported_event_is_ignored_without_repository_write() -> None:
    repository = InMemoryRepository()
    use_case = ProjectFrontendWorkflowEvent(
        projector=SourceIngestionFrontendWorkflowEventProjector(),
        repository=repository,
    )

    result = await use_case.execute(_unsupported_event())

    assert result is None
    assert repository.events == {}
