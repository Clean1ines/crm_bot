from __future__ import annotations

from typing import Protocol

from src.application.ports.knowledge.documents import KnowledgeDbPoolPort
from src.application.ports.knowledge_artifact_cleanup import (
    KnowledgeArtifactCleanupPort,
)


class KnowledgeArtifactCleanupRepositoryFactoryPort(Protocol):
    def __call__(self, pool: KnowledgeDbPoolPort) -> KnowledgeArtifactCleanupPort: ...


__all__ = [
    "KnowledgeArtifactCleanupPort",
    "KnowledgeArtifactCleanupRepositoryFactoryPort",
]
