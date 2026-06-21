from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.application.ports.frontend_workflow_event_repository_port import (
    FrontendWorkflowEventRepositoryPort,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent


class FrontendWorkflowEventProjectorPort(Protocol):
    def project(self, event: WorkflowEvent) -> FrontendWorkflowEvent | None: ...


@dataclass(frozen=True, slots=True)
class ProjectFrontendWorkflowEvent:
    """Projects one allowlisted workflow event and persists it idempotently."""

    projector: FrontendWorkflowEventProjectorPort
    repository: FrontendWorkflowEventRepositoryPort

    async def execute(self, event: WorkflowEvent) -> FrontendWorkflowEvent | None:
        projected = self.projector.project(event)
        if projected is None:
            return None
        return await self.repository.append(projected)
