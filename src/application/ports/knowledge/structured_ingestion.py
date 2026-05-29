from __future__ import annotations

from typing import Protocol

from src.application.ports.knowledge.answer_candidates import (
    KnowledgeAnswerCandidatePort,
)
from src.application.ports.knowledge.artifact_cleanup import (
    KnowledgeArtifactCleanupPort,
)
from src.application.ports.knowledge.canonical_entries import (
    KnowledgeCanonicalEntryPort,
)
from src.application.ports.knowledge.compilation_trace import (
    KnowledgeCompilationTracePort,
)
from src.application.ports.knowledge.documents import (
    KnowledgeDbPoolPort,
    KnowledgeDocumentPort,
)
from src.application.ports.knowledge.runtime_retrieval import (
    KnowledgeRuntimeRetrievalPort,
)
from src.application.ports.knowledge.source_material import KnowledgeSourceMaterialPort


class KnowledgeStructuredIngestionRepositoryPort(
    KnowledgeDocumentPort,
    KnowledgeSourceMaterialPort,
    KnowledgeCompilationTracePort,
    KnowledgeAnswerCandidatePort,
    KnowledgeCanonicalEntryPort,
    KnowledgeRuntimeRetrievalPort,
    KnowledgeArtifactCleanupPort,
    Protocol,
):
    """Repository surface for non-FAQ structured document ingestion."""


class KnowledgeStructuredIngestionRepositoryFactoryPort(Protocol):
    def __call__(
        self,
        pool: KnowledgeDbPoolPort,
    ) -> KnowledgeStructuredIngestionRepositoryPort: ...


__all__ = [
    "KnowledgeStructuredIngestionRepositoryFactoryPort",
    "KnowledgeStructuredIngestionRepositoryPort",
]
