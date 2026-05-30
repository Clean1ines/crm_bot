from __future__ import annotations


from dataclasses import dataclass
from src.application.ports.commercial_price import CommercialPriceKnowledgePort
from src.application.ports.commercial_price_acquisition import (
    CommercialPriceAcquisitionServicePort,
)
from src.application.ports.knowledge import (
    KnowledgeAnswerCandidatePort,
    KnowledgeCanonicalEntryPort,
    KnowledgeCompilationTracePort,
    KnowledgeDocumentPort,
    KnowledgeRuntimeRetrievalPort,
    KnowledgeSourceMaterialPort,
)
from src.application.ports.knowledge_port import KnowledgeDbPoolPort
from src.domain.project_plane.knowledge_artifact_cleanup import (
    KnowledgeArtifactCleanupPlan,
    KnowledgeArtifactCleanupResult,
)
from typing import Protocol


class KnowledgeIngestionRepositoryPort(
    KnowledgeDocumentPort,
    KnowledgeSourceMaterialPort,
    KnowledgeCompilationTracePort,
    KnowledgeAnswerCandidatePort,
    KnowledgeCanonicalEntryPort,
    KnowledgeRuntimeRetrievalPort,
    Protocol,
):
    """Repository subset required by knowledge ingestion workflows."""

    async def cleanup_document_artifacts(
        self,
        plan: KnowledgeArtifactCleanupPlan,
    ) -> KnowledgeArtifactCleanupResult: ...


class CommercialPriceAcquisitionServiceFactoryPort(Protocol):
    def __call__(self) -> CommercialPriceAcquisitionServicePort: ...


class CommercialPriceRepositoryFactoryPort(Protocol):
    def __call__(self, pool: KnowledgeDbPoolPort) -> CommercialPriceKnowledgePort: ...


class KnowledgeIngestionRepositoryFactoryPort(Protocol):
    def __call__(
        self, pool: KnowledgeDbPoolPort
    ) -> KnowledgeIngestionRepositoryPort: ...


@dataclass(frozen=True, slots=True)
class KnowledgeDocumentProcessingResult:
    document_id: str
    preprocessing_status: str
    structured_entries: int


__all__ = [
    "KnowledgeDocumentProcessingResult",
    "KnowledgeIngestionRepositoryPort",
    "KnowledgeIngestionRepositoryFactoryPort",
    "CommercialPriceAcquisitionServiceFactoryPort",
    "CommercialPriceRepositoryFactoryPort",
]
