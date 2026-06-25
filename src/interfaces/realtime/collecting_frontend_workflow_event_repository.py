from __future__ import annotations

from dataclasses import dataclass, field

from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event_cursor import (
    FrontendWorkflowEventCursor,
)
from src.contexts.knowledge_workbench.observability.application.ports.frontend_workflow_event_repository_port import (
    FrontendWorkflowEventRepositoryPort,
)


@dataclass(slots=True)
class CollectingFrontendWorkflowEventRepository(FrontendWorkflowEventRepositoryPort):
    """Transaction-local wrapper that remembers persisted frontend events.

    The wrapped repository remains the source of persistence. This wrapper only
    collects the events returned by append() so the composition root can publish
    them to the realtime transport after the surrounding transaction commits.
    """

    inner: FrontendWorkflowEventRepositoryPort
    _persisted_events: list[FrontendWorkflowEvent] = field(default_factory=list)

    async def append(self, event: FrontendWorkflowEvent) -> FrontendWorkflowEvent:
        persisted = await self.inner.append(event)
        self._persisted_events.append(persisted)
        return persisted

    async def list_frontend_events(
        self,
        workflow_run_id: str,
        after_cursor: FrontendWorkflowEventCursor,
        limit: int,
    ) -> tuple[FrontendWorkflowEvent, ...]:
        return await self.inner.list_frontend_events(
            workflow_run_id,
            after_cursor,
            limit,
        )

    def persisted_events(self) -> tuple[FrontendWorkflowEvent, ...]:
        return tuple(self._persisted_events)
