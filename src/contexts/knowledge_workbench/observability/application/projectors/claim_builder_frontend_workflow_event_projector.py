from __future__ import annotations

from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.application.projectors.claim_builder_dispatch_batch_frontend_workflow_event_projector import (
    ClaimBuilderDispatchBatchFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.application.projectors.claim_builder_section_outcome_frontend_workflow_event_projector import (
    ClaimBuilderSectionOutcomeFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.application.projectors.claim_builder_work_scheduling_frontend_workflow_event_projector import (
    ClaimBuilderWorkSchedulingFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.application.projectors.llm_provider_capacity_observed_frontend_workflow_event_projector import (
    LlmProviderCapacityObservedFrontendWorkflowEventProjector,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent


class ClaimBuilderFrontendWorkflowEventProjector:
    """Routes knowledge-extraction canonical events to frontend projectors."""

    def __init__(self) -> None:
        self._scheduling = ClaimBuilderWorkSchedulingFrontendWorkflowEventProjector()
        self._dispatch_batch = ClaimBuilderDispatchBatchFrontendWorkflowEventProjector()
        self._capacity_observed = (
            LlmProviderCapacityObservedFrontendWorkflowEventProjector()
        )
        self._section_outcome = (
            ClaimBuilderSectionOutcomeFrontendWorkflowEventProjector()
        )

    def project(self, event: WorkflowEvent) -> FrontendWorkflowEvent | None:
        projected = self._scheduling.project(event)
        if projected is not None:
            return projected
        projected = self._dispatch_batch.project(event)
        if projected is not None:
            return projected
        projected = self._capacity_observed.project(event)
        if projected is not None:
            return projected
        return self._section_outcome.project(event)
