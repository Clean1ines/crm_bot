from __future__ import annotations

from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.jsonb_payload_hydration import (
    hydrate_jsonb_object_payload,
)
from collections.abc import Mapping
from datetime import datetime
from typing import Protocol, cast

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_cluster_preview import (
    DraftClaimClusterPreview,
    DraftClaimClusterPreviewBuildResult,
)
from src.domain.project_plane.json_types import JsonObject


class DraftClaimClusterPreviewConnectionLike(Protocol):
    async def execute(self, query: str, *args: object) -> str: ...

    async def fetchrow(self, query: str, *args: object) -> object | None: ...


class PostgresDraftClaimClusterPreviewRepository:
    def __init__(self, connection: DraftClaimClusterPreviewConnectionLike) -> None:
        self._connection = connection

    async def save_preview(
        self,
        preview: DraftClaimClusterPreview,
    ) -> DraftClaimClusterPreviewBuildResult:
        existing = await self.load_preview(workflow_run_id=preview.workflow_run_id)
        await self._connection.execute(
            """
            INSERT INTO draft_claim_cluster_previews (
                workflow_run_id,
                preview_payload,
                claim_count,
                group_count,
                created_at,
                updated_at
            )
            VALUES ($1, $2::jsonb, $3, $4, $5, $6)
            ON CONFLICT (workflow_run_id) DO UPDATE
            SET preview_payload = EXCLUDED.preview_payload,
                claim_count = EXCLUDED.claim_count,
                group_count = EXCLUDED.group_count,
                updated_at = EXCLUDED.updated_at
            """,
            preview.workflow_run_id,
            preview.to_payload(),
            preview.claim_count,
            preview.group_count,
            preview.created_at,
            preview.updated_at,
        )
        return DraftClaimClusterPreviewBuildResult(
            workflow_run_id=preview.workflow_run_id,
            claim_count=preview.claim_count,
            group_count=preview.group_count,
            created_preview=existing is None,
            updated_preview=existing is not None,
        )

    async def load_preview(
        self,
        *,
        workflow_run_id: str,
    ) -> DraftClaimClusterPreview | None:
        row = await self._connection.fetchrow(
            """
            SELECT workflow_run_id,
                   preview_payload,
                   created_at,
                   updated_at
            FROM draft_claim_cluster_previews
            WHERE workflow_run_id = $1
            """,
            workflow_run_id,
        )
        if row is None:
            return None
        row_mapping = cast(Mapping[str, object], row)
        return DraftClaimClusterPreview.from_payload(
            workflow_run_id=_row_text(row_mapping, "workflow_run_id"),
            payload=_preview_payload(row_mapping.get("preview_payload")),
            created_at=_row_datetime(row_mapping, "created_at"),
            updated_at=_row_datetime(row_mapping, "updated_at"),
        )


def _preview_payload(value: object) -> JsonObject:
    return cast(
        JsonObject,
        dict(
            hydrate_jsonb_object_payload(
                value,
                field_name="draft_claim_cluster_previews.preview_payload",
            )
        ),
    )


def _row_text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty str")
    return value


def _row_datetime(row: Mapping[str, object], key: str) -> datetime:
    value = row.get(key)
    if not isinstance(value, datetime):
        raise ValueError(f"{key} must be datetime")
    return value
