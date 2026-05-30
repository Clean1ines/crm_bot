from __future__ import annotations

from src.application.ports.knowledge.answer_candidates import (
    KnowledgeAnswerCandidatePort,
)
from src.application.ports.knowledge.artifact_cleanup import (
    KnowledgeArtifactCleanupPort,
    KnowledgeArtifactCleanupRepositoryFactoryPort,
)
from src.application.ports.knowledge.failed_batch_retry import (
    KnowledgeFailedBatchRetryRepositoryFactoryPort,
    KnowledgeFailedBatchRetryRepositoryPort,
)
from src.application.ports.knowledge.canonical_entries import (
    KnowledgeCanonicalEntryPort,
)
from src.application.ports.knowledge.compilation_trace import (
    KnowledgeCompilationTracePort,
)
from src.application.ports.knowledge.curation import KnowledgeCurationPort
from src.application.ports.knowledge.documents import (
    KnowledgeDbPoolPort,
    KnowledgeDocumentPort,
    KnowledgeDocumentRuntimeEntries,
)
from src.application.ports.knowledge.runtime_retrieval import (
    KnowledgeRuntimeRetrievalPort,
)
from src.application.ports.knowledge.source_import import (
    KnowledgeSourceImportRepositoryFactoryPort,
    KnowledgeSourceImportRepositoryPort,
)
from src.application.ports.knowledge.source_material import KnowledgeSourceMaterialPort
from src.application.ports.knowledge.structured_ingestion import (
    KnowledgeStructuredIngestionRepositoryFactoryPort,
    KnowledgeStructuredIngestionRepositoryPort,
)
from src.application.ports.knowledge.ready_answer_publication import (
    KnowledgeReadyAnswerPublicationRepositoryFactoryPort,
    KnowledgeReadyAnswerPublicationRepositoryPort,
    KnowledgeStageEPublicationPort,
)
from src.application.ports.knowledge.retighten import (
    KnowledgeRetightenRepositoryFactoryPort,
    KnowledgeRetightenRepositoryPort,
)
from src.application.ports.knowledge.surface_compiler_runs import (
    KnowledgeSurfaceCompilerRunPort,
)
from src.application.ports.knowledge.surface_compiler_stages import (
    KnowledgeSurfaceCompilerStagePort,
)
from src.application.ports.knowledge.surface_entities import (
    KnowledgeSurfaceDraftPort,
    KnowledgeSurfaceMergeDecisionPort,
    KnowledgeSurfaceQuestionOwnershipPort,
    KnowledgeSurfaceRelationPort,
    KnowledgeSurfaceSourceUnitPort,
)
from src.application.ports.knowledge.surface_graph_entities import (
    KnowledgeSurfaceAnswerDraftPort,
    KnowledgeSurfaceCandidatePort,
    KnowledgeSurfaceCurationCardPort,
    KnowledgeSurfaceGraphQuestionPort,
    KnowledgeSurfaceGraphRelationPort,
    KnowledgeSurfaceReconciliationPort,
)
from src.application.ports.knowledge.surface_publication import (
    KnowledgeSurfacePublicationPort,
)

from src.application.ports.knowledge.production_retrieval import (
    ProductionRetrievalPort,
    ProductionRetrievalRequest,
    ProductionRetrievalResult,
    ProductionRetrievalResultItem,
)

__all__ = [
    "KnowledgeStructuredIngestionRepositoryPort",
    "KnowledgeStructuredIngestionRepositoryFactoryPort",
    "KnowledgeStageEPublicationPort",
    "KnowledgeSourceImportRepositoryPort",
    "KnowledgeSourceImportRepositoryFactoryPort",
    "KnowledgeRetightenRepositoryPort",
    "KnowledgeRetightenRepositoryFactoryPort",
    "KnowledgeReadyAnswerPublicationRepositoryPort",
    "KnowledgeReadyAnswerPublicationRepositoryFactoryPort",
    "KnowledgeFailedBatchRetryRepositoryPort",
    "KnowledgeFailedBatchRetryRepositoryFactoryPort",
    "KnowledgeArtifactCleanupRepositoryFactoryPort",
    "KnowledgeArtifactCleanupPort",
    "KnowledgeAnswerCandidatePort",
    "KnowledgeCanonicalEntryPort",
    "KnowledgeCompilationTracePort",
    "KnowledgeCurationPort",
    "KnowledgeDbPoolPort",
    "KnowledgeDocumentPort",
    "KnowledgeDocumentRuntimeEntries",
    "KnowledgeRuntimeRetrievalPort",
    "KnowledgeSourceMaterialPort",
    "KnowledgeSurfaceAnswerDraftPort",
    "KnowledgeSurfaceCandidatePort",
    "KnowledgeSurfaceCompilerRunPort",
    "KnowledgeSurfaceCompilerStagePort",
    "KnowledgeSurfaceCurationCardPort",
    "KnowledgeSurfaceDraftPort",
    "KnowledgeSurfaceGraphQuestionPort",
    "KnowledgeSurfaceGraphRelationPort",
    "KnowledgeSurfaceMergeDecisionPort",
    "KnowledgeSurfacePublicationPort",
    "KnowledgeSurfaceQuestionOwnershipPort",
    "KnowledgeSurfaceReconciliationPort",
    "KnowledgeSurfaceRelationPort",
    "KnowledgeSurfaceSourceUnitPort",
    "ProductionRetrievalPort",
    "ProductionRetrievalRequest",
    "ProductionRetrievalResult",
    "ProductionRetrievalResultItem",
]
