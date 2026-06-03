from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.domain.project_plane.json_types import JsonValue


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


class FaqWorkbenchRuntimePublicationService:
    def __init__(
        self,
        repository: FaqWorkbenchRuntimePublicationRepositoryPort,
    ) -> None:
        self._repository = repository

    async def publish_fact_registry_runtime_entries(
        self,
        command: PublishFactRegistryRuntimeCommand,
    ) -> PublishFactRegistryRuntimeResult:
        count = await self._repository.publish_fact_registry_runtime_entries(
            project_id=command.project_id,
            document_id=command.document_id,
            fact_registry_payload=command.fact_registry_payload,
        )
        return PublishFactRegistryRuntimeResult(published_entry_count=count)


__all__ = [
    "FaqWorkbenchRuntimePublicationRepositoryPort",
    "FaqWorkbenchRuntimePublicationService",
    "PublishFactRegistryRuntimeCommand",
    "PublishFactRegistryRuntimeResult",
]
