from __future__ import annotations

import inspect
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.interfaces.http import dependencies, knowledge
from tests.api.test_knowledge import _FakeProjectRepo, _user_repo


def _event(
    *,
    workflow_run_id: str = "workflow-1",
    project_id: str = "project-1",
    document_id: str = "document-1",
) -> FrontendWorkflowEvent:
    occurred_at = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    return FrontendWorkflowEvent(
        projection_event_id="projection-1",
        source_event_id="source-event-1",
        source_sequence_number=17,
        projection_version=1,
        projection_type="workflow_source_units_created",
        event_type="SourceUnitsCreated",
        operation_key="ingest_source_document",
        canonical_phase="SOURCE_INGESTION",
        workflow_run_id=workflow_run_id,
        project_id=project_id,
        document_id=document_id,
        payload={"source_document_ref": document_id, "source_unit_count": 3},
        occurred_at=occurred_at,
        projected_at=occurred_at,
    )


class FakePool:
    @asynccontextmanager
    async def acquire(self):
        yield object()


class FakeFrontendWorkflowEventRepository:
    events: tuple[FrontendWorkflowEvent, ...] = ()
    calls: list[tuple[str, int, int]] = []

    def __init__(self, connection: object) -> None:
        del connection

    async def list_frontend_events(
        self,
        workflow_run_id: str,
        after_source_sequence: int,
        limit: int,
    ) -> tuple[FrontendWorkflowEvent, ...]:
        self.calls.append((workflow_run_id, after_source_sequence, limit))
        return self.events


async def _allow_auth(authorization: str | None) -> str:
    del authorization
    return "user-1"


@pytest.fixture(autouse=True)
def _reset_repository() -> None:
    FakeFrontendWorkflowEventRepository.events = ()
    FakeFrontendWorkflowEventRepository.calls = []


@pytest.mark.asyncio
async def test_frontend_workflow_events_endpoint_returns_projection_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeFrontendWorkflowEventRepository.events = (_event(),)
    monkeypatch.setattr(dependencies, "get_current_user_id", _allow_auth)
    monkeypatch.setattr(
        knowledge,
        "PostgresFrontendWorkflowEventRepository",
        FakeFrontendWorkflowEventRepository,
    )

    response = await knowledge.list_knowledge_frontend_workflow_events(
        project_id="project-1",
        document_id="document-1",
        workflow_run_id="workflow-1",
        after_source_sequence=10,
        limit=25,
        authorization="Bearer token",
        pool=FakePool(),
        project_repo=_FakeProjectRepo(has_role=True),
        user_repo=_user_repo(),
    )

    assert FakeFrontendWorkflowEventRepository.calls == [("workflow-1", 10, 25)]
    assert response["events"] == [
        {
            "projection_event_id": "projection-1",
            "source_event_id": "source-event-1",
            "source_sequence_number": 17,
            "projection_version": 1,
            "projection_type": "workflow_source_units_created",
            "event_type": "SourceUnitsCreated",
            "operation_key": "ingest_source_document",
            "canonical_phase": "SOURCE_INGESTION",
            "workflow_run_id": "workflow-1",
            "project_id": "project-1",
            "document_id": "document-1",
            "payload": {
                "source_document_ref": "document-1",
                "source_unit_count": 3,
            },
            "occurred_at": "2026-06-21T12:00:00+00:00",
            "causation_command_id": None,
            "correlation_id": None,
        }
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event", "project_id", "document_id", "workflow_run_id"),
    (
        (_event(project_id="project-2"), "project-1", "document-1", "workflow-1"),
        (_event(document_id="document-2"), "project-1", "document-1", "workflow-1"),
        (_event(workflow_run_id="workflow-2"), "project-1", "document-1", "workflow-1"),
    ),
)
async def test_frontend_workflow_events_endpoint_does_not_leak_other_scope(
    monkeypatch: pytest.MonkeyPatch,
    event: FrontendWorkflowEvent,
    project_id: str,
    document_id: str,
    workflow_run_id: str,
) -> None:
    FakeFrontendWorkflowEventRepository.events = (event,)
    monkeypatch.setattr(dependencies, "get_current_user_id", _allow_auth)
    monkeypatch.setattr(
        knowledge,
        "PostgresFrontendWorkflowEventRepository",
        FakeFrontendWorkflowEventRepository,
    )

    response = await knowledge.list_knowledge_frontend_workflow_events(
        project_id=project_id,
        document_id=document_id,
        workflow_run_id=workflow_run_id,
        after_source_sequence=0,
        limit=100,
        authorization="Bearer token",
        pool=FakePool(),
        project_repo=_FakeProjectRepo(has_role=True),
        user_repo=_user_repo(),
    )

    assert response["events"] == []


@pytest.mark.asyncio
async def test_frontend_workflow_events_endpoint_returns_empty_list_without_drain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbidden_call(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("workflow runner, drain, or live-state must not be called")

    monkeypatch.setattr(dependencies, "get_current_user_id", _allow_auth)
    monkeypatch.setattr(
        knowledge,
        "PostgresFrontendWorkflowEventRepository",
        FakeFrontendWorkflowEventRepository,
    )
    monkeypatch.setattr(
        knowledge, "_drain_workflow_from_live_state_poll", forbidden_call
    )
    monkeypatch.setattr(
        knowledge,
        "fetch_workbench_workflow_live_state",
        forbidden_call,
    )

    response = await knowledge.list_knowledge_frontend_workflow_events(
        project_id="project-1",
        document_id="document-1",
        workflow_run_id="workflow-1",
        after_source_sequence=0,
        limit=100,
        authorization="Bearer token",
        pool=FakePool(),
        project_repo=_FakeProjectRepo(has_role=True),
        user_repo=_user_repo(),
    )

    assert response == {
        "workflow_run_id": "workflow-1",
        "after_source_sequence": 0,
        "events": [],
    }


def test_frontend_workflow_events_endpoint_is_projection_only_source_guard() -> None:
    source = inspect.getsource(knowledge.list_knowledge_frontend_workflow_events)

    assert "PostgresFrontendWorkflowEventRepository" in source
    for forbidden_marker in (
        "drain",
        "live_state",
        "workflow_runner",
        "make_knowledge_extraction",
        "execution_runtime",
        "capacity",
        "background_tasks",
    ):
        assert forbidden_marker not in source
