from __future__ import annotations

from collections.abc import Mapping
import json
from datetime import datetime
from typing import Protocol

from src.contexts.knowledge_workbench.curation.application.models.draft_claim_curation_workspace import (
    DraftClaimCurationItemEditablePayload,
    DraftClaimCurationWorkspace,
    DraftClaimCurationWorkspaceItem,
    DraftClaimCurationWorkspaceSnapshot,
    DraftClaimCurationWorkspaceStatus,
)
from src.contexts.knowledge_workbench.curation.application.ports.draft_claim_curation_workspace_repository_port import (
    DraftClaimCurationWorkspaceRepositoryPort,
)


class DraftClaimCurationWorkspaceConnectionLike(Protocol):
    async def execute(self, query: str, *args: object) -> object: ...

    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]: ...

    async def fetchrow(
        self,
        query: str,
        *args: object,
    ) -> Mapping[str, object] | None: ...


class PostgresDraftClaimCurationWorkspaceRepository(
    DraftClaimCurationWorkspaceRepositoryPort
):
    def __init__(self, connection: DraftClaimCurationWorkspaceConnectionLike) -> None:
        self._connection = connection

    async def get_workspace_by_workflow_run_id(
        self,
        *,
        workflow_run_id: str,
    ) -> DraftClaimCurationWorkspaceSnapshot | None:
        row = await self._connection.fetchrow(
            """
            SELECT workspace_ref, workflow_run_id, project_id, source_document_ref,
                   status, created_at, updated_at
            FROM draft_claim_curation_workspaces
            WHERE workflow_run_id = $1
            """,
            workflow_run_id,
        )
        if row is None:
            return None
        workspace = _workspace(row)
        return DraftClaimCurationWorkspaceSnapshot(
            workspace=workspace,
            items=await self.list_items(workspace_ref=workspace.workspace_ref),
        )

    async def get_item(
        self,
        *,
        item_ref: str,
    ) -> DraftClaimCurationWorkspaceItem | None:
        row = await self._connection.fetchrow(
            _ITEM_SELECT + " WHERE item_ref = $1",
            item_ref,
        )
        if row is None:
            return None
        return _item(row)

    async def create_workspace(
        self,
        *,
        workspace: DraftClaimCurationWorkspace,
        items: tuple[DraftClaimCurationWorkspaceItem, ...],
    ) -> DraftClaimCurationWorkspaceSnapshot:
        await self._connection.execute(
            """
            INSERT INTO draft_claim_curation_workspaces (
                workspace_ref, workflow_run_id, project_id, source_document_ref,
                status, created_at, updated_at
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7)
            ON CONFLICT (workflow_run_id) DO NOTHING
            """,
            workspace.workspace_ref,
            workspace.workflow_run_id,
            workspace.project_id,
            workspace.source_document_ref,
            workspace.status.value,
            workspace.created_at,
            workspace.updated_at,
        )
        for item in items:
            await self._connection.execute(
                """
                INSERT INTO draft_claim_curation_items (
                    item_ref, workspace_ref, workflow_run_id, group_ref,
                    compacted_node_ref, source_claim_refs, original_payload,
                    editable_payload, excluded, exclusion_reason,
                    created_at, updated_at
                )
                VALUES ($1,$2,$3,$4,$5,$6::jsonb,$7::jsonb,$8::jsonb,$9,$10,$11,$12)
                ON CONFLICT (workspace_ref, compacted_node_ref) DO NOTHING
                """,
                item.item_ref,
                item.workspace_ref,
                item.workflow_run_id,
                item.group_ref,
                item.compacted_node_ref,
                json.dumps(list(item.source_claim_refs)),
                json.dumps(item.original_payload.to_json_dict()),
                json.dumps(item.editable_payload.to_json_dict()),
                item.excluded,
                item.exclusion_reason,
                item.created_at,
                item.updated_at,
            )
        snapshot = await self.get_workspace_by_workflow_run_id(
            workflow_run_id=workspace.workflow_run_id,
        )
        if snapshot is None:
            raise RuntimeError("curation workspace was not created")
        return snapshot

    async def list_items(
        self,
        *,
        workspace_ref: str,
    ) -> tuple[DraftClaimCurationWorkspaceItem, ...]:
        rows = await self._connection.fetch(
            _ITEM_SELECT
            + """
            WHERE workspace_ref = $1
            ORDER BY group_ref, compacted_node_ref, item_ref
            """,
            workspace_ref,
        )
        return tuple(_item(row) for row in rows)

    async def replace_item_editable_payload(
        self,
        *,
        item_ref: str,
        editable_payload: DraftClaimCurationItemEditablePayload,
        updated_at: datetime,
    ) -> DraftClaimCurationWorkspaceItem:
        await self._connection.execute(
            """
            UPDATE draft_claim_curation_items
            SET editable_payload = $2::jsonb,
                updated_at = $3
            WHERE item_ref = $1
            """,
            item_ref,
            json.dumps(editable_payload.to_json_dict()),
            updated_at,
        )
        row = await self._connection.fetchrow(
            _ITEM_SELECT + " WHERE item_ref = $1",
            item_ref,
        )
        if row is None:
            raise ValueError("draft claim curation item was not found")
        return _item(row)

    async def set_item_excluded(
        self,
        *,
        item_ref: str,
        excluded: bool,
        exclusion_reason: str | None,
        updated_at: datetime,
    ) -> DraftClaimCurationWorkspaceItem:
        await self._connection.execute(
            """
            UPDATE draft_claim_curation_items
            SET excluded = $2,
                exclusion_reason = $3,
                updated_at = $4
            WHERE item_ref = $1
            """,
            item_ref,
            excluded,
            exclusion_reason,
            updated_at,
        )
        row = await self._connection.fetchrow(
            _ITEM_SELECT + " WHERE item_ref = $1",
            item_ref,
        )
        if row is None:
            raise ValueError("draft claim curation item was not found")
        return _item(row)


_ITEM_SELECT = """
SELECT item_ref, workspace_ref, workflow_run_id, group_ref, compacted_node_ref,
       source_claim_refs, original_payload, editable_payload, excluded,
       exclusion_reason, created_at, updated_at
FROM draft_claim_curation_items
"""


def _workspace(row: Mapping[str, object]) -> DraftClaimCurationWorkspace:
    return DraftClaimCurationWorkspace(
        workspace_ref=_str(row, "workspace_ref"),
        workflow_run_id=_str(row, "workflow_run_id"),
        project_id=_optional_str(row, "project_id"),
        source_document_ref=_optional_str(row, "source_document_ref"),
        status=DraftClaimCurationWorkspaceStatus(_str(row, "status")),
        created_at=_datetime(row, "created_at"),
        updated_at=_datetime(row, "updated_at"),
    )


def _item(row: Mapping[str, object]) -> DraftClaimCurationWorkspaceItem:
    return DraftClaimCurationWorkspaceItem(
        item_ref=_str(row, "item_ref"),
        workspace_ref=_str(row, "workspace_ref"),
        workflow_run_id=_str(row, "workflow_run_id"),
        group_ref=_str(row, "group_ref"),
        compacted_node_ref=_str(row, "compacted_node_ref"),
        source_claim_refs=tuple(
            _str_list(row["source_claim_refs"], "source_claim_refs")
        ),
        original_payload=DraftClaimCurationItemEditablePayload.from_payload(
            _mapping(row["original_payload"], "original_payload")
        ),
        editable_payload=DraftClaimCurationItemEditablePayload.from_payload(
            _mapping(row["editable_payload"], "editable_payload")
        ),
        excluded=_bool(row, "excluded"),
        exclusion_reason=_optional_str(row, "exclusion_reason"),
        created_at=_datetime(row, "created_at"),
        updated_at=_datetime(row, "updated_at"),
    )


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if isinstance(value, str):
        decoded = json.loads(value)
        if not isinstance(decoded, Mapping):
            raise TypeError(f"{field_name} must decode to object")
        return decoded
    if not isinstance(value, Mapping):
        raise TypeError(f"{field_name} must be object")
    return value


def _str(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be non-empty str")
    return value


def _optional_str(row: Mapping[str, object], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be non-empty str when set")
    return value


def _bool(row: Mapping[str, object], key: str) -> bool:
    value = row.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be bool")
    return value


def _datetime(row: Mapping[str, object], key: str) -> datetime:
    value = row.get(key)
    if not isinstance(value, datetime):
        raise TypeError(f"{key} must be datetime")
    return value


def _str_list(value: object, field_name: str) -> list[str]:
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, list):
        raise TypeError(f"{field_name} must be list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise TypeError(f"{field_name} must contain non-empty strings")
        result.append(item)
    return result
