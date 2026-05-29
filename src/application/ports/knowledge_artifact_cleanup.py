from __future__ import annotations

from typing import Protocol

from src.domain.project_plane.knowledge_artifact_cleanup import (
    KnowledgeArtifactCleanupPlan,
    KnowledgeArtifactCleanupResult,
)


class KnowledgeArtifactCleanupPort(Protocol):
    async def cleanup_document_artifacts(
        self,
        plan: KnowledgeArtifactCleanupPlan,
    ) -> KnowledgeArtifactCleanupResult:
        """Clean artifacts for a single knowledge document according to a domain plan."""

    async def cleanup_project_artifacts(
        self,
        plan: KnowledgeArtifactCleanupPlan,
    ) -> KnowledgeArtifactCleanupResult:
        """Clean knowledge artifacts for a whole project according to a domain plan."""
