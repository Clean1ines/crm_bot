from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from src.domain.project_plane.knowledge_workbench import DomainInvariantError


class PublishReadyRejectedError(DomainInvariantError):
    """Raised when a document has no reconciled fact-registry snapshot to publish."""


class FaqWorkbenchPublishReadyRepositoryPort(Protocol):
    async def publish_latest_reconciled_fact_registry_snapshot(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> str | None: ...


@dataclass(frozen=True, slots=True)
class PublishReadyCommand:
    project_id: str
    document_id: str

    def __post_init__(self) -> None:
        if not self.project_id:
            raise DomainInvariantError("publish-ready command requires project_id")
        if not self.document_id:
            raise DomainInvariantError("publish-ready command requires document_id")


@dataclass(frozen=True, slots=True)
class PublishReadyResult:
    project_id: str
    document_id: str
    published_snapshot_id: str
    published: bool = True


class FaqWorkbenchPublishReadyService:
    def __init__(
        self,
        repository: FaqWorkbenchPublishReadyRepositoryPort,
    ) -> None:
        self._repository = repository

    async def publish_ready(
        self,
        command: PublishReadyCommand,
    ) -> PublishReadyResult:
        snapshot_id = (
            await self._repository.publish_latest_reconciled_fact_registry_snapshot(
                project_id=command.project_id,
                document_id=command.document_id,
            )
        )
        if snapshot_id is None:
            raise PublishReadyRejectedError(
                "no reconciled fact registry snapshot is ready to publish"
            )

        return PublishReadyResult(
            project_id=command.project_id,
            document_id=command.document_id,
            published_snapshot_id=snapshot_id,
        )


__all__ = [
    "FaqWorkbenchPublishReadyRepositoryPort",
    "FaqWorkbenchPublishReadyService",
    "PublishReadyCommand",
    "PublishReadyRejectedError",
    "PublishReadyResult",
]
