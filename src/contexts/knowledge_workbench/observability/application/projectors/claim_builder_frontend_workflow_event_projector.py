from __future__ import annotations

from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.application.projectors.claim_builder_dispatch_batch_frontend_workflow_event_projector import (
    ClaimBuilderDispatchBatchFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.application.projectors.claim_builder_work_scheduling_frontend_workflow_event_projector import (
    ClaimBuilderWorkSchedulingFrontendWorkflowEventProjector,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent


class ClaimBuilderFrontendWorkflowEventProjector:
    """Routes claim-builder canonical events to their frontend projectors."""

    def __init__(self) -> None:
        self._scheduling = ClaimBuilderWorkSchedulingFrontendWorkflowEventProjector()
        self._dispatch_batch = ClaimBuilderDispatchBatchFrontendWorkflowEventProjector()

    def project(self, event: WorkflowEvent) -> FrontendWorkflowEvent | None:
        projected = self._scheduling.project(event)
        if projected is not None:
            return projected
        return self._dispatch_batch.project(event)
