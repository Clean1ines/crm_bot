from __future__ import annotations

from typing import Protocol, runtime_checkable

from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent
from src.contexts.workflow_runtime.domain.value_objects.workflow_consumer_ref import (
    WorkflowConsumerRef,
)


@runtime_checkable
class OutboxRepositoryPort(Protocol):
    async def append_event(
        self,
        event: WorkflowEvent,
    ) -> WorkflowEvent: ...

    async def list_events_after(
        self,
        *,
        consumer_ref: WorkflowConsumerRef,
        after_sequence_number: int,
        limit: int,
    ) -> tuple[WorkflowEvent, ...]: ...
