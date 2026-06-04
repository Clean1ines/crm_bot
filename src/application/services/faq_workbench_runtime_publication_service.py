from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.domain.project_plane.json_types import JsonObject, JsonValue
from src.application.services.faq_workbench_retrieval_surface_publication_service import (
    FaqWorkbenchRetrievalSurfacePublicationService,
    PublishWorkbenchFactRetrievalSurfaceCommand,
)


class FaqWorkbenchRuntimePublicationRepositoryPort(Protocol):
    async def publish_fact_registry_runtime_entries(
        self,
        *,
        project_id: str,
        document_id: str,
        fact_registry_payload: JsonValue,
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class PublishFactRegistryRuntimeCommand:
    project_id: str
    document_id: str
    fact_registry_payload: JsonValue


@dataclass(frozen=True, slots=True)
class PublishFactRegistryRuntimeResult:
    published_entry_count: int
    published_retrieval_surface_entry_count: int = 0


class FaqWorkbenchRuntimePublicationService:
    """Publish Workbench facts into both projections.

    1. knowledge_workbench_runtime_retrieval_entries remains a Workbench
       observability/debug projection.
    2. knowledge_retrieval_surface is the customer runtime vector+FTS projection
       consumed by SearchKnowledgeTool/RAGService.
    """

    def __init__(
        self,
        repository: FaqWorkbenchRuntimePublicationRepositoryPort,
        retrieval_surface_publication_service: FaqWorkbenchRetrievalSurfacePublicationService
        | None = None,
    ) -> None:
        self._repository = repository
        self._retrieval_surface_publication_service = (
            retrieval_surface_publication_service
        )

    async def publish_fact_registry_runtime_entries(
        self,
        command: PublishFactRegistryRuntimeCommand,
    ) -> PublishFactRegistryRuntimeResult:
        count = await self._repository.publish_fact_registry_runtime_entries(
            project_id=command.project_id,
            document_id=command.document_id,
            fact_registry_payload=command.fact_registry_payload,
        )

        retrieval_surface_count = 0
        if self._retrieval_surface_publication_service is not None and isinstance(
            command.fact_registry_payload, dict
        ):
            retrieval_surface_result = await self._retrieval_surface_publication_service.publish_workbench_fact_retrieval_surface(
                PublishWorkbenchFactRetrievalSurfaceCommand(
                    project_id=command.project_id,
                    document_id=command.document_id,
                    fact_registry_payload=JsonObject(command.fact_registry_payload),
                )
            )
            retrieval_surface_count = retrieval_surface_result.published_entry_count

        return PublishFactRegistryRuntimeResult(
            published_entry_count=count,
            published_retrieval_surface_entry_count=retrieval_surface_count,
        )


__all__ = [
    "FaqWorkbenchRuntimePublicationRepositoryPort",
    "FaqWorkbenchRuntimePublicationService",
    "PublishFactRegistryRuntimeCommand",
    "PublishFactRegistryRuntimeResult",
]
