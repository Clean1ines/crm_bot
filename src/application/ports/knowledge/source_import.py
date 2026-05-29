from __future__ import annotations

from typing import Protocol

from src.application.ports.knowledge.artifact_cleanup import (
    KnowledgeArtifactCleanupPort,
)
from src.application.ports.knowledge.documents import (
    KnowledgeDbPoolPort,
    KnowledgeDocumentPort,
)
from src.application.ports.knowledge.source_material import KnowledgeSourceMaterialPort


class KnowledgeSourceImportRepositoryPort(
    KnowledgeDocumentPort,
    KnowledgeSourceMaterialPort,
    KnowledgeArtifactCleanupPort,
    Protocol,
):
    """Repository surface for importing source material into a knowledge document."""


class KnowledgeSourceImportRepositoryFactoryPort(Protocol):
    def __call__(
        self,
        pool: KnowledgeDbPoolPort,
    ) -> KnowledgeSourceImportRepositoryPort: ...


__all__ = [
    "KnowledgeSourceImportRepositoryFactoryPort",
    "KnowledgeSourceImportRepositoryPort",
]
