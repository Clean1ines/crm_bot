from __future__ import annotations

from src.contexts.knowledge_workbench.observability.application.models.frontend_workflow_event import (
    FrontendWorkflowEvent,
)
from src.contexts.knowledge_workbench.observability.application.projectors.claim_builder_frontend_workflow_event_projector import (
    ClaimBuilderFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.application.projectors.draft_claim_compaction_frontend_workflow_event_projector import (
    DraftClaimCompactionFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.application.projectors.draft_claim_cluster_frontend_workflow_event_projector import (
    DraftClaimClusterFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.application.projectors.draft_claim_embedding_frontend_workflow_event_projector import (
    DraftClaimEmbeddingFrontendWorkflowEventProjector,
)
from src.contexts.knowledge_workbench.observability.application.projectors.source_ingestion_frontend_workflow_event_projector import (
    SourceIngestionFrontendWorkflowEventProjector,
)
from src.contexts.workflow_runtime.domain.entities.workflow_event import WorkflowEvent


class KnowledgeExtractionFrontendWorkflowEventProjector:
    """Routes knowledge-extraction canonical events to bounded frontend projectors."""

    def __init__(self) -> None:
        self._source_ingestion = SourceIngestionFrontendWorkflowEventProjector()
        self._claim_builder = ClaimBuilderFrontendWorkflowEventProjector()
        self._draft_claim_embedding = (
            DraftClaimEmbeddingFrontendWorkflowEventProjector()
        )
        self._draft_claim_cluster = DraftClaimClusterFrontendWorkflowEventProjector()
        self._draft_claim_compaction = (
            DraftClaimCompactionFrontendWorkflowEventProjector()
        )

    def project(self, event: WorkflowEvent) -> FrontendWorkflowEvent | None:
        projected = self._source_ingestion.project(event)
        if projected is not None:
            return projected
        projected = self._claim_builder.project(event)
        if projected is not None:
            return projected
        projected = self._draft_claim_embedding.project(event)
        if projected is not None:
            return projected
        projected = self._draft_claim_cluster.project(event)
        if projected is not None:
            return projected
        return self._draft_claim_compaction.project(event)
