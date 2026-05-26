from __future__ import annotations

from src.application.ports.knowledge.answer_candidates import (
    KnowledgeAnswerCandidatePort,
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
from src.application.ports.knowledge.source_material import KnowledgeSourceMaterialPort
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
from src.application.ports.knowledge.surface_publication import (
    KnowledgeSurfacePublicationPort,
)

__all__ = [
    "KnowledgeAnswerCandidatePort",
    "KnowledgeCanonicalEntryPort",
    "KnowledgeCompilationTracePort",
    "KnowledgeCurationPort",
    "KnowledgeDbPoolPort",
    "KnowledgeDocumentPort",
    "KnowledgeDocumentRuntimeEntries",
    "KnowledgeRuntimeRetrievalPort",
    "KnowledgeSourceMaterialPort",
    "KnowledgeSurfacePublicationPort",
    "KnowledgeSurfaceMergeDecisionPort",
    "KnowledgeSurfaceQuestionOwnershipPort",
    "KnowledgeSurfaceRelationPort",
    "KnowledgeSurfaceDraftPort",
    "KnowledgeSurfaceSourceUnitPort",
    "KnowledgeSurfaceCompilerStagePort",
    "KnowledgeSurfaceCompilerRunPort",
]
