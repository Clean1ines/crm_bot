from __future__ import annotations

from dataclasses import dataclass

from src.application.ports.knowledge_artifact_cleanup import (
    KnowledgeArtifactCleanupPort,
)
from src.domain.project_plane.knowledge_artifact_cleanup import (
    SCOPE_DOCUMENT,
    SCOPE_PROJECT,
    KnowledgeArtifactCleanupPlan,
    KnowledgeArtifactCleanupResult,
    build_document_delete_cleanup_plan,
    build_document_reset_cleanup_plan,
    build_manual_cancel_cleanup_plan,
    build_project_clear_cleanup_plan,
)


@dataclass(frozen=True)
class KnowledgeArtifactCleanupService:
    repository: KnowledgeArtifactCleanupPort

    async def cleanup(
        self,
        plan: KnowledgeArtifactCleanupPlan,
    ) -> KnowledgeArtifactCleanupResult:
        if plan.scope == SCOPE_DOCUMENT:
            return await self.repository.cleanup_document_artifacts(plan)

        if plan.scope == SCOPE_PROJECT:
            return await self.repository.cleanup_project_artifacts(plan)

        raise ValueError(f"unsupported cleanup scope: {plan.scope}")

    async def manual_cancel_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> KnowledgeArtifactCleanupResult:
        return await self.cleanup(
            build_manual_cancel_cleanup_plan(
                project_id=project_id,
                document_id=document_id,
            )
        )

    async def reset_document_for_reprocess(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> KnowledgeArtifactCleanupResult:
        return await self.cleanup(
            build_document_reset_cleanup_plan(
                project_id=project_id,
                document_id=document_id,
            )
        )

    async def delete_document(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> KnowledgeArtifactCleanupResult:
        return await self.cleanup(
            build_document_delete_cleanup_plan(
                project_id=project_id,
                document_id=document_id,
            )
        )

    async def clear_project(
        self,
        *,
        project_id: str,
    ) -> KnowledgeArtifactCleanupResult:
        return await self.cleanup(
            build_project_clear_cleanup_plan(project_id=project_id)
        )
