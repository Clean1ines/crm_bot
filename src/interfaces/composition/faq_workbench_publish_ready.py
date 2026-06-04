from __future__ import annotations

from typing import Callable, Protocol, cast

import asyncpg

from src.application.services.faq_workbench_retrieval_surface_publication_service import (
    FaqWorkbenchRetrievalSurfacePublicationService,
    PublishWorkbenchFactRetrievalSurfaceCommand,
)
from src.application.services.faq_workbench_runtime_publication_service import (
    FaqWorkbenchRuntimePublicationService,
    PublishFactRegistryRuntimeCommand,
)
from src.application.workbench_commands.publish_ready import (
    FaqWorkbenchPublishReadyService,
    PublishReadyCommand,
    PublishReadyRejectedError,
)
from src.domain.project_plane.knowledge_workbench.shared import JsonValue
from src.infrastructure.db.knowledge_workbench_repository import (
    KnowledgeWorkbenchRepository,
)
from src.infrastructure.db.workbench_retrieval_surface_repository import (
    WorkbenchRetrievalSurfaceRepository,
)
from src.infrastructure.db.workbench_runtime_retrieval_repository import (
    WorkbenchRuntimeRetrievalRepository,
)
from src.infrastructure.llm.workbench_retrieval_surface_embedding_adapter import (
    WorkbenchRetrievalSurfaceEmbeddingAdapter,
)


class WorkbenchPublishReadyDbPool(Protocol):
    async def acquire(self): ...


async def publish_workbench_ready_surfaces(
    *,
    pool: WorkbenchPublishReadyDbPool,
    project_id: str,
    document_id: str,
) -> dict[str, object]:
    async with cast(asyncpg.Pool, pool).acquire() as connection:
        async with connection.transaction():
            repository = _workbench_repository(connection)
            service = FaqWorkbenchPublishReadyService(repository)
            result = await service.publish_ready(
                PublishReadyCommand(
                    project_id=project_id,
                    document_id=document_id,
                )
            )

            fact_registry_payload = await _load_published_fact_registry_payload(
                connection=connection,
                project_id=result.project_id,
                document_id=result.document_id,
                snapshot_id=result.published_snapshot_id,
            )

            retrieval_surface_publication = (
                FaqWorkbenchRetrievalSurfacePublicationService(
                    repository=WorkbenchRetrievalSurfaceRepository(connection),
                    embedding_service=WorkbenchRetrievalSurfaceEmbeddingAdapter(),
                )
            )
            runtime_publication = FaqWorkbenchRuntimePublicationService(
                WorkbenchRuntimeRetrievalRepository(cast(asyncpg.Pool, pool)),
                retrieval_surface_publication,
            )
            runtime_result = (
                await runtime_publication.publish_fact_registry_runtime_entries(
                    PublishFactRegistryRuntimeCommand(
                        project_id=result.project_id,
                        document_id=result.document_id,
                        fact_registry_payload=cast(JsonValue, fact_registry_payload),
                    )
                )
            )

            retrieval_surface_publication = (
                FaqWorkbenchRetrievalSurfacePublicationService(
                    repository=WorkbenchRetrievalSurfaceRepository(connection),
                    embedding_service=WorkbenchRetrievalSurfaceEmbeddingAdapter(),
                )
            )
            retrieval_surface_result = await retrieval_surface_publication.publish_workbench_fact_retrieval_surface(
                PublishWorkbenchFactRetrievalSurfaceCommand(
                    project_id=result.project_id,
                    document_id=result.document_id,
                    fact_registry_payload=fact_registry_payload,
                )
            )

            return {
                "project_id": result.project_id,
                "document_id": result.document_id,
                "published_snapshot_id": result.published_snapshot_id,
                "published": result.published,
                "published_runtime_entry_count": runtime_result.published_entry_count,
                "published_retrieval_surface_entry_count": (
                    retrieval_surface_result.published_entry_count
                ),
            }


async def _load_published_fact_registry_payload(
    *,
    connection: asyncpg.Connection,
    project_id: str,
    document_id: str,
    snapshot_id: str,
) -> dict[str, object]:
    row = await connection.fetchrow(
        """
        SELECT entries_payload
        FROM knowledge_workbench_registry_snapshots
        WHERE project_id = $1::uuid
          AND document_id = $2
          AND snapshot_id = $3
          AND is_final_published IS TRUE
        LIMIT 1
        """,
        project_id,
        document_id,
        snapshot_id,
    )
    if row is None:
        raise PublishReadyRejectedError(
            "published fact registry snapshot payload is unavailable"
        )

    entries_payload = row["entries_payload"]
    if not isinstance(entries_payload, dict):
        raise PublishReadyRejectedError(
            "published fact registry snapshot payload must be an object"
        )

    fact_registry = entries_payload.get("fact_registry")
    if isinstance(fact_registry, dict):
        return dict(fact_registry)

    if isinstance(entries_payload.get("canonical_facts"), list) and isinstance(
        entries_payload.get("fact_relations"), list
    ):
        return dict(entries_payload)

    raise PublishReadyRejectedError(
        "published snapshot does not contain fact_registry payload"
    )


def _workbench_repository(connection: object) -> KnowledgeWorkbenchRepository:
    factory = cast(
        Callable[[object], KnowledgeWorkbenchRepository],
        KnowledgeWorkbenchRepository,
    )
    return factory(connection)


__all__ = [
    "PublishReadyRejectedError",
    "_load_published_fact_registry_payload",
    "publish_workbench_ready_surfaces",
]
