from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping, cast

import asyncpg

from src.application.services.commercial_price_review_service import (
    CommercialPriceReviewService,
)
from src.infrastructure.db.repositories.commercial_price_repository import (
    CommercialPriceRepository,
)


@dataclass(frozen=True, slots=True)
class CommercialKnowledgeDocumentMetadata:
    id: str
    project_id: str
    file_name: str
    preprocessing_mode: str | None
    metadata: Mapping[str, object]
    created_at: datetime | None
    updated_at: datetime | None


class CommercialKnowledgeDocumentMetadataRepository:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def get_document(
        self, document_id: str
    ) -> CommercialKnowledgeDocumentMetadata | None:
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT
                    id,
                    project_id,
                    file_name,
                    preprocessing_mode,
                    metadata,
                    created_at,
                    updated_at
                FROM knowledge_documents
                WHERE id = $1::uuid
                """,
                document_id,
            )

        if row is None:
            return None

        metadata = row["metadata"]
        return CommercialKnowledgeDocumentMetadata(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            file_name=str(row["file_name"] or ""),
            preprocessing_mode=str(row["preprocessing_mode"])
            if row["preprocessing_mode"] is not None
            else None,
            metadata=cast(
                Mapping[str, object], metadata if isinstance(metadata, dict) else {}
            ),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )


def make_commercial_price_review_service(
    pool: asyncpg.Pool,
) -> CommercialPriceReviewService:
    return CommercialPriceReviewService(
        repo=CommercialPriceRepository(pool),
        knowledge_document_repo=CommercialKnowledgeDocumentMetadataRepository(pool),
    )
