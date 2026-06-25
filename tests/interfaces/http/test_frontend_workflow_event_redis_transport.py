from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.interfaces.realtime.redis_frontend_workflow_event_bus import (
    RedisFrontendWorkflowEventSubscription,
    frontend_workflow_event_from_json,
    frontend_workflow_event_to_json,
)


def _event() -> FrontendWorkflowEvent:
    occurred_at = datetime(2026, 6, 21, 12, 0, tzinfo=timezone.utc)
    return FrontendWorkflowEvent(
        projection_event_id="projection-1",
        source_event_id="source-1",
        source_sequence_number=7,
        projection_version=1,
        projection_type="workflow_source_units_created",
        event_type="SourceUnitsCreated",
        operation_key="ingest_source_document",
        canonical_phase="SOURCE_INGESTION",
        workflow_run_id="workflow-1",
        project_id="project-1",
        document_id="document-1",
        payload={"source_unit_count": 3},
        occurred_at=occurred_at,
        causation_command_id=None,
        correlation_id=None,
        projected_at=occurred_at,
    )


def test_frontend_workflow_event_json_roundtrip() -> None:
    event = _event()

    restored = frontend_workflow_event_from_json(frontend_workflow_event_to_json(event))

    assert restored == event


class _FakePubSub:
    def __init__(self, message: object) -> None:
        self.message = message

    async def get_message(
        self,
        *,
        ignore_subscribe_messages: bool,
        timeout: float,
    ) -> object:
        assert ignore_subscribe_messages is True
        assert timeout == 15.0
        return self.message


@pytest.mark.asyncio
async def test_subscription_ignores_non_payload_messages() -> None:
    subscription = RedisFrontendWorkflowEventSubscription(
        pubsub=_FakePubSub({"type": "subscribe", "data": 1}),
    )

    assert await subscription.next_event(timeout_seconds=15.0) is None


@pytest.mark.asyncio
async def test_subscription_decodes_frontend_event_payload() -> None:
    event = _event()
    subscription = RedisFrontendWorkflowEventSubscription(
        pubsub=_FakePubSub(
            {"type": "message", "data": frontend_workflow_event_to_json(event)}
        ),
    )

    assert await subscription.next_event(timeout_seconds=15.0) == event
