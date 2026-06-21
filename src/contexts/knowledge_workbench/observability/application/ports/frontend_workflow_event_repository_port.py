from __future__ import annotations

from typing import Protocol

from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)


class FrontendWorkflowEventRepositoryPort(Protocol):
    async def append(self, event: FrontendWorkflowEvent) -> FrontendWorkflowEvent: ...

    async def list_frontend_events(
        self,
        workflow_run_id: str,
        after_source_sequence: int,
        limit: int,
    ) -> tuple[FrontendWorkflowEvent, ...]: ...
