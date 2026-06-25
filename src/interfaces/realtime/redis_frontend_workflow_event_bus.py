from __future__ import annotations

import json
from collections.abc import Mapping
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast

from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.redis.client import get_redis_client

logger = get_logger(__name__)

_FRONTEND_WORKFLOW_EVENT_CHANNEL_PREFIX = "frontend-workflow-events"


class _RedisPubSubLike(Protocol):
    async def subscribe(self, *channels: str) -> object: ...

    async def unsubscribe(self, *channels: str) -> object: ...

    async def close(self) -> object: ...

    async def get_message(
        self,
        *,
        ignore_subscribe_messages: bool,
        timeout: float,
    ) -> object: ...


class _RedisClientLike(Protocol):
    async def publish(self, channel: str, message: str) -> object: ...

    def pubsub(self) -> _RedisPubSubLike: ...


@dataclass(frozen=True, slots=True)
class RedisFrontendWorkflowEventSubscription:
    pubsub: _RedisPubSubLike

    async def next_event(
        self,
        *,
        timeout_seconds: float,
    ) -> FrontendWorkflowEvent | None:
        message = await self.pubsub.get_message(
            ignore_subscribe_messages=True,
            timeout=timeout_seconds,
        )
        if not isinstance(message, Mapping):
            return None

        raw_data = message.get("data")
        if not isinstance(raw_data, str) or not raw_data.strip():
            return None

        return frontend_workflow_event_from_json(raw_data)


async def publish_frontend_workflow_events(
    events: tuple[FrontendWorkflowEvent, ...],
) -> None:
    """Best-effort publish of already persisted frontend projection events.

    Redis is transport only. Failed Redis publish must not rollback or fail the
    committed workflow transaction.
    """

    if not events:
        return

    try:
        redis_client = cast(_RedisClientLike, await get_redis_client())
        for event in events:
            await redis_client.publish(
                _frontend_workflow_event_channel(event.workflow_run_id),
                frontend_workflow_event_to_json(event),
            )
    except Exception as exc:
        logger.warning(
            "Frontend workflow event Redis publish failed",
            extra={"error": str(exc)},
        )


@asynccontextmanager
async def subscribe_frontend_workflow_events(
    *,
    workflow_run_id: str,
):
    redis_client = cast(_RedisClientLike, await get_redis_client())
    pubsub = redis_client.pubsub()
    channel = _frontend_workflow_event_channel(workflow_run_id)
    await pubsub.subscribe(channel)
    try:
        yield RedisFrontendWorkflowEventSubscription(pubsub=pubsub)
    finally:
        await pubsub.unsubscribe(channel)
        await pubsub.close()


def frontend_workflow_event_to_json(event: FrontendWorkflowEvent) -> str:
    return json.dumps(
        {
            "projection_event_id": event.projection_event_id,
            "source_event_id": event.source_event_id,
            "source_sequence_number": event.source_sequence_number,
            "projection_version": event.projection_version,
            "projection_type": event.projection_type,
            "event_type": event.event_type,
            "operation_key": event.operation_key,
            "canonical_phase": event.canonical_phase,
            "workflow_run_id": event.workflow_run_id,
            "project_id": event.project_id,
            "document_id": event.document_id,
            "payload": dict(event.payload),
            "occurred_at": event.occurred_at.isoformat(),
            "causation_command_id": event.causation_command_id,
            "correlation_id": event.correlation_id,
            "projected_at": event.projected_at.isoformat(),
        },
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def frontend_workflow_event_from_json(raw: str) -> FrontendWorkflowEvent:
    decoded = json.loads(raw)
    if not isinstance(decoded, Mapping):
        raise TypeError("frontend workflow event message must decode to object")

    return FrontendWorkflowEvent(
        projection_event_id=_required_str(decoded, "projection_event_id"),
        source_event_id=_required_str(decoded, "source_event_id"),
        source_sequence_number=_required_int(decoded, "source_sequence_number"),
        projection_version=_required_int(decoded, "projection_version"),
        projection_type=_required_str(decoded, "projection_type"),
        event_type=_required_str(decoded, "event_type"),
        operation_key=_optional_str(decoded, "operation_key"),
        canonical_phase=_required_str(decoded, "canonical_phase"),
        workflow_run_id=_required_str(decoded, "workflow_run_id"),
        project_id=_required_str(decoded, "project_id"),
        document_id=_required_str(decoded, "document_id"),
        payload=_required_payload(decoded, "payload"),
        occurred_at=_required_datetime(decoded, "occurred_at"),
        causation_command_id=_optional_str(decoded, "causation_command_id"),
        correlation_id=_optional_str(decoded, "correlation_id"),
        projected_at=_required_datetime(decoded, "projected_at"),
    )


def _frontend_workflow_event_channel(workflow_run_id: str) -> str:
    if not isinstance(workflow_run_id, str) or not workflow_run_id.strip():
        raise ValueError("workflow_run_id must be non-empty")
    return f"{_FRONTEND_WORKFLOW_EVENT_CHANNEL_PREFIX}:{workflow_run_id}"


def _required_str(payload: Mapping[str, object], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be non-empty string")
    return value


def _optional_str(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be null or non-empty string")
    return value


def _required_int(payload: Mapping[str, object], key: str) -> int:
    value = payload[key]
    if not isinstance(value, int) or isinstance(value, bool):
        raise TypeError(f"{key} must be int")
    return value


def _required_payload(payload: Mapping[str, object], key: str) -> Mapping[str, object]:
    value = payload[key]
    if not isinstance(value, Mapping):
        raise TypeError(f"{key} must be object")
    return value


def _required_datetime(payload: Mapping[str, object], key: str) -> datetime:
    value = payload[key]
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be ISO datetime string")
    return datetime.fromisoformat(value)
