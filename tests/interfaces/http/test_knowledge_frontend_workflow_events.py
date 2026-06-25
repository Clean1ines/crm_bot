from __future__ import annotations

import inspect
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import cast

import pytest
from starlette.requests import Request
from starlette.responses import StreamingResponse

from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event_cursor import (
    FrontendWorkflowEventCursor,
)
from src.interfaces.http import dependencies, knowledge
from tests.api.test_knowledge import _FakeProjectRepo, _user_repo


def _event(
    *,
    projection_event_id: str = "projection-1",
    source_event_id: str = "source-event-1",
    source_sequence_number: int = 17,
    projection_type: str = "workflow_source_units_created",
    projection_version: int = 1,
    workflow_run_id: str = "workflow-1",
    project_id: str = "project-1",
    document_id: str = "document-1",
) -> FrontendWorkflowEvent:
    occurred_at = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    return FrontendWorkflowEvent(
        projection_event_id=projection_event_id,
        source_event_id=source_event_id,
        source_sequence_number=source_sequence_number,
        projection_version=projection_version,
        projection_type=projection_type,
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
    calls: list[tuple[str, FrontendWorkflowEventCursor, int]] = []

    def __init__(self, connection: object) -> None:
        del connection

    async def list_frontend_events(
        self,
        workflow_run_id: str,
        after_cursor: FrontendWorkflowEventCursor,
        limit: int,
    ) -> tuple[FrontendWorkflowEvent, ...]:
        self.calls.append((workflow_run_id, after_cursor, limit))
        return tuple(
            sorted(
                (
                    event
                    for event in self.events
                    if event.workflow_run_id == workflow_run_id
                    and _event_is_after_cursor(event, after_cursor)
                ),
                key=lambda event: (
                    event.source_sequence_number,
                    event.projection_type,
                    event.projection_version,
                    event.projection_event_id,
                ),
            )[:limit]
        )


def _event_is_after_cursor(
    event: FrontendWorkflowEvent,
    after_cursor: FrontendWorkflowEventCursor,
) -> bool:
    if after_cursor.sequence_only:
        return event.source_sequence_number > after_cursor.source_sequence_number
    return (
        event.source_sequence_number,
        event.projection_type,
        event.projection_version,
        event.projection_event_id,
    ) > (
        after_cursor.source_sequence_number,
        after_cursor.projection_type,
        after_cursor.projection_version,
        after_cursor.projection_event_id,
    )


class FakeRequest:
    def __init__(self, *, disconnect_after_checks: int = 0) -> None:
        self._remaining_checks = disconnect_after_checks

    async def is_disconnected(self) -> bool:
        if self._remaining_checks <= 0:
            return True
        self._remaining_checks -= 1
        return False


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

    assert FakeFrontendWorkflowEventRepository.calls == [
        (
            "workflow-1",
            FrontendWorkflowEventCursor.from_legacy_source_sequence(10),
            25,
        )
    ]
    assert response["after_source_sequence"] == 10
    assert response["after_cursor"] is None
    assert response["next_cursor"] is not None
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
        knowledge, "make_knowledge_extraction_workflow_resume", forbidden_call
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
        "after_cursor": None,
        "next_cursor": None,
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


@pytest.mark.asyncio
async def test_frontend_workflow_event_stream_replays_in_composite_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeFrontendWorkflowEventRepository.events = (
        _event(
            projection_event_id="projection-c",
            source_sequence_number=12,
            projection_type="z",
        ),
        _event(
            projection_event_id="projection-b",
            source_sequence_number=11,
            projection_type="z",
        ),
        _event(
            projection_event_id="projection-d",
            source_sequence_number=11,
            projection_type="a",
            projection_version=2,
        ),
        _event(
            projection_event_id="projection-a",
            source_sequence_number=11,
            projection_type="a",
        ),
    )
    monkeypatch.setattr(dependencies, "get_current_user_id", _allow_auth)
    monkeypatch.setattr(
        knowledge,
        "PostgresFrontendWorkflowEventRepository",
        FakeFrontendWorkflowEventRepository,
    )

    response = await knowledge.stream_knowledge_frontend_workflow_events(
        project_id="project-1",
        document_id="document-1",
        workflow_run_id="workflow-1",
        request=cast(Request, FakeRequest()),
        after_source_sequence=10,
        authorization="Bearer token",
        pool=FakePool(),
        project_repo=_FakeProjectRepo(has_role=True),
        user_repo=_user_repo(),
    )

    assert isinstance(response, StreamingResponse)
    chunks = [chunk async for chunk in response.body_iterator]
    text = "".join(
        chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks
    )
    assert tuple(
        line.removeprefix("id: ")
        for line in text.splitlines()
        if line.startswith("id: ")
    ) == (
        "projection-a",
        "projection-d",
        "projection-b",
        "projection-c",
    )
    assert FakeFrontendWorkflowEventRepository.calls == [
        (
            "workflow-1",
            FrontendWorkflowEventCursor.from_legacy_source_sequence(10),
            200,
        )
    ]


@pytest.mark.asyncio
async def test_frontend_workflow_event_stream_cursor_and_scope_are_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeFrontendWorkflowEventRepository.events = (
        _event(projection_event_id="old", source_sequence_number=10),
        _event(projection_event_id="visible", source_sequence_number=11),
        _event(
            projection_event_id="wrong-project",
            source_sequence_number=12,
            project_id="project-2",
        ),
        _event(
            projection_event_id="wrong-document",
            source_sequence_number=13,
            document_id="document-2",
        ),
    )
    monkeypatch.setattr(dependencies, "get_current_user_id", _allow_auth)
    monkeypatch.setattr(
        knowledge,
        "PostgresFrontendWorkflowEventRepository",
        FakeFrontendWorkflowEventRepository,
    )

    response = await knowledge.stream_knowledge_frontend_workflow_events(
        project_id="project-1",
        document_id="document-1",
        workflow_run_id="workflow-1",
        request=cast(Request, FakeRequest()),
        after_source_sequence=10,
        authorization="Bearer token",
        pool=FakePool(),
        project_repo=_FakeProjectRepo(has_role=True),
        user_repo=_user_repo(),
    )

    chunks = [chunk async for chunk in response.body_iterator]
    text = "".join(
        chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks
    )
    assert "id: visible" in text
    assert "id: old" not in text
    assert "wrong-project" not in text
    assert "wrong-document" not in text


@pytest.mark.asyncio
async def test_frontend_workflow_event_stream_does_not_call_runtime_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def forbidden_call(*args: object, **kwargs: object) -> None:
        del args, kwargs
        raise AssertionError("runtime, drain, or live-state must not be called")

    monkeypatch.setattr(dependencies, "get_current_user_id", _allow_auth)
    monkeypatch.setattr(
        knowledge,
        "PostgresFrontendWorkflowEventRepository",
        FakeFrontendWorkflowEventRepository,
    )
    monkeypatch.setattr(
        knowledge, "make_knowledge_extraction_workflow_resume", forbidden_call
    )
    monkeypatch.setattr(
        knowledge,
        "fetch_workbench_workflow_live_state",
        forbidden_call,
    )
    monkeypatch.setattr(
        knowledge,
        "resume_knowledge_extraction_workflow",
        forbidden_call,
    )

    response = await knowledge.stream_knowledge_frontend_workflow_events(
        project_id="project-1",
        document_id="document-1",
        workflow_run_id="workflow-1",
        request=cast(Request, FakeRequest()),
        after_source_sequence=0,
        authorization="Bearer token",
        pool=FakePool(),
        project_repo=_FakeProjectRepo(has_role=True),
        user_repo=_user_repo(),
    )

    assert [chunk async for chunk in response.body_iterator] == []


@pytest.mark.asyncio
async def test_frontend_workflow_event_stream_waits_for_redis_after_empty_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeFrontendWorkflowEventSubscription:
        def __init__(self) -> None:
            self._events = [
                _event(projection_event_id="projection-from-redis"),
                None,
            ]

        async def next_event(
            self,
            *,
            timeout_seconds: float,
        ) -> FrontendWorkflowEvent | None:
            assert timeout_seconds == 15.0
            if not self._events:
                return None
            return self._events.pop(0)

    @asynccontextmanager
    async def fake_subscribe_frontend_workflow_events(
        *,
        workflow_run_id: str,
    ):
        assert workflow_run_id == "workflow-1"
        yield FakeFrontendWorkflowEventSubscription()

    monkeypatch.setattr(dependencies, "get_current_user_id", _allow_auth)
    monkeypatch.setattr(
        knowledge,
        "PostgresFrontendWorkflowEventRepository",
        FakeFrontendWorkflowEventRepository,
    )
    monkeypatch.setattr(
        knowledge,
        "subscribe_frontend_workflow_events",
        fake_subscribe_frontend_workflow_events,
    )

    response = await knowledge.stream_knowledge_frontend_workflow_events(
        project_id="project-1",
        document_id="document-1",
        workflow_run_id="workflow-1",
        request=cast(Request, FakeRequest(disconnect_after_checks=2)),
        after_source_sequence=0,
        authorization="Bearer token",
        pool=FakePool(),
        project_repo=_FakeProjectRepo(has_role=True),
        user_repo=_user_repo(),
    )

    chunks = [chunk async for chunk in response.body_iterator]
    text = "".join(
        chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks
    )
    assert "id: projection-from-redis" in text
    assert FakeFrontendWorkflowEventRepository.calls == [
        (
            "workflow-1",
            FrontendWorkflowEventCursor.from_legacy_source_sequence(0),
            200,
        )
    ]


def test_frontend_workflow_event_stream_is_projection_only_source_guard() -> None:
    source = inspect.getsource(knowledge.stream_knowledge_frontend_workflow_events)

    assert "PostgresFrontendWorkflowEventRepository" in source
    assert "subscribe_frontend_workflow_events" in source
    assert "await asyncio.sleep" not in source
    assert "workflow_live_state_changed" not in source
    for forbidden_marker in (
        "fetch_workbench_workflow_live_state",
        "_drain_workflow_from_live_state_poll",
        "resume_knowledge_extraction_workflow",
        "workflow_runner",
        "execution_runtime",
        "capacity",
        "add_listener",
    ):
        assert forbidden_marker not in source


@pytest.mark.asyncio
async def test_frontend_workflow_events_legacy_after_source_sequence_still_works(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    FakeFrontendWorkflowEventRepository.events = (
        _event(projection_event_id="seq-10-a", source_sequence_number=10),
        _event(projection_event_id="seq-11-a", source_sequence_number=11),
    )
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
        limit=100,
        authorization="Bearer token",
        pool=FakePool(),
        project_repo=_FakeProjectRepo(has_role=True),
        user_repo=_user_repo(),
    )

    assert [event["projection_event_id"] for event in response["events"]] == [
        "seq-11-a"
    ]
    assert response["after_cursor"] is None


@pytest.mark.asyncio
async def test_frontend_workflow_events_composite_cursor_continues_same_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _event(
        projection_event_id="projection-a",
        source_sequence_number=11,
        projection_type="a",
    )
    second = _event(
        projection_event_id="projection-b",
        source_sequence_number=11,
        projection_type="b",
    )
    FakeFrontendWorkflowEventRepository.events = (first, second)
    monkeypatch.setattr(dependencies, "get_current_user_id", _allow_auth)
    monkeypatch.setattr(
        knowledge,
        "PostgresFrontendWorkflowEventRepository",
        FakeFrontendWorkflowEventRepository,
    )

    after_cursor = FrontendWorkflowEventCursor.from_event(first).serialize()
    response = await knowledge.list_knowledge_frontend_workflow_events(
        project_id="project-1",
        document_id="document-1",
        workflow_run_id="workflow-1",
        after_cursor=after_cursor,
        after_source_sequence=99,
        limit=100,
        authorization="Bearer token",
        pool=FakePool(),
        project_repo=_FakeProjectRepo(has_role=True),
        user_repo=_user_repo(),
    )

    assert [event["projection_event_id"] for event in response["events"]] == [
        "projection-b"
    ]
    assert FakeFrontendWorkflowEventRepository.calls[0][1] == (
        FrontendWorkflowEventCursor.parse(after_cursor)
    )


@pytest.mark.asyncio
async def test_frontend_workflow_events_pages_within_one_source_sequence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events = tuple(
        _event(
            projection_event_id=f"projection-{index:03d}",
            source_sequence_number=42,
            projection_type="workflow_source_units_created",
            projection_version=1,
        )
        for index in range(250)
    )
    FakeFrontendWorkflowEventRepository.events = events
    monkeypatch.setattr(dependencies, "get_current_user_id", _allow_auth)
    monkeypatch.setattr(
        knowledge,
        "PostgresFrontendWorkflowEventRepository",
        FakeFrontendWorkflowEventRepository,
    )

    first_page = await knowledge.list_knowledge_frontend_workflow_events(
        project_id="project-1",
        document_id="document-1",
        workflow_run_id="workflow-1",
        after_source_sequence=0,
        limit=200,
        authorization="Bearer token",
        pool=FakePool(),
        project_repo=_FakeProjectRepo(has_role=True),
        user_repo=_user_repo(),
    )

    assert len(first_page["events"]) == 200
    assert first_page["next_cursor"] is not None

    second_page = await knowledge.list_knowledge_frontend_workflow_events(
        project_id="project-1",
        document_id="document-1",
        workflow_run_id="workflow-1",
        after_cursor=first_page["next_cursor"],
        limit=200,
        authorization="Bearer token",
        pool=FakePool(),
        project_repo=_FakeProjectRepo(has_role=True),
        user_repo=_user_repo(),
    )

    assert len(second_page["events"]) == 50
    assert second_page["next_cursor"] is not None
    assert first_page["events"][-1]["projection_event_id"] == "projection-199"
    assert second_page["events"][0]["projection_event_id"] == "projection-200"


@pytest.mark.asyncio
async def test_frontend_workflow_events_rejects_invalid_cursor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(dependencies, "get_current_user_id", _allow_auth)
    monkeypatch.setattr(
        knowledge,
        "PostgresFrontendWorkflowEventRepository",
        FakeFrontendWorkflowEventRepository,
    )

    with pytest.raises(knowledge.HTTPException) as exc_info:
        await knowledge.list_knowledge_frontend_workflow_events(
            project_id="project-1",
            document_id="document-1",
            workflow_run_id="workflow-1",
            after_cursor="not-a-valid-cursor",
            limit=100,
            authorization="Bearer token",
            pool=FakePool(),
            project_repo=_FakeProjectRepo(has_role=True),
            user_repo=_user_repo(),
        )

    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_frontend_workflow_event_stream_uses_composite_cursor_for_replay(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = _event(
        projection_event_id="projection-a",
        source_sequence_number=11,
        projection_type="a",
    )
    second = _event(
        projection_event_id="projection-b",
        source_sequence_number=11,
        projection_type="b",
    )
    FakeFrontendWorkflowEventRepository.events = (first, second)
    monkeypatch.setattr(dependencies, "get_current_user_id", _allow_auth)
    monkeypatch.setattr(
        knowledge,
        "PostgresFrontendWorkflowEventRepository",
        FakeFrontendWorkflowEventRepository,
    )

    after_cursor = FrontendWorkflowEventCursor.from_event(first).serialize()
    response = await knowledge.stream_knowledge_frontend_workflow_events(
        project_id="project-1",
        document_id="document-1",
        workflow_run_id="workflow-1",
        request=cast(Request, FakeRequest()),
        after_cursor=after_cursor,
        authorization="Bearer token",
        pool=FakePool(),
        project_repo=_FakeProjectRepo(has_role=True),
        user_repo=_user_repo(),
    )

    chunks = [chunk async for chunk in response.body_iterator]
    text = "".join(
        chunk.decode() if isinstance(chunk, bytes) else chunk for chunk in chunks
    )
    assert "id: projection-b" in text
    assert "id: projection-a" not in text
    assert FakeFrontendWorkflowEventRepository.calls[0][1] == (
        FrontendWorkflowEventCursor.parse(after_cursor)
    )
