from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_reduction_models import (
    DraftClaimCompactionNode,
)
from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_cluster_preview import (
    DraftClaimClusterPreview,
    DraftClaimClusterPreviewBuildResult,
    DraftClaimClusterPreviewClaim,
    DraftClaimClusterPreviewGroup,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_cluster_preview_repository_port import (
    DraftClaimClusterPreviewRepositoryPort,
)
from src.contexts.knowledge_workbench.extraction.application.ports.draft_claim_compaction_reduction_state_repository_port import (
    DraftClaimCompactionReductionStateRepositoryPort,
)
from src.domain.project_plane.json_types import JsonObject, JsonValue


class DraftClaimClusterPreviewBuildError(RuntimeError):
    pass


class DraftClaimCompactionPreviewReadRepositoryPort(
    DraftClaimCompactionReductionStateRepositoryPort,
    Protocol,
):
    async def count_active_raw_nodes(
        self,
        *,
        workflow_run_id: str,
    ) -> int: ...

    async def list_final_compacted_nodes_for_preview(
        self,
        *,
        workflow_run_id: str,
    ) -> tuple[DraftClaimCompactionNode, ...]: ...


@dataclass(frozen=True, slots=True)
class BuildDraftClaimClusterPreview:
    compaction_reduction_state_repository: DraftClaimCompactionPreviewReadRepositoryPort
    cluster_preview_repository: DraftClaimClusterPreviewRepositoryPort

    async def execute(
        self,
        *,
        workflow_run_id: str,
        created_at: datetime,
    ) -> DraftClaimClusterPreviewBuildResult:
        active_raw_count = (
            await self.compaction_reduction_state_repository.count_active_raw_nodes(
                workflow_run_id=workflow_run_id,
            )
        )
        if active_raw_count:
            raise DraftClaimClusterPreviewBuildError(
                "cannot build cluster preview while active raw nodes remain"
            )

        compacted_nodes = await self.compaction_reduction_state_repository.list_final_compacted_nodes_for_preview(
            workflow_run_id=workflow_run_id,
        )
        if not compacted_nodes:
            raise DraftClaimClusterPreviewBuildError(
                "cannot build cluster preview without active compacted nodes"
            )

        groups = _preview_groups_from_nodes(compacted_nodes)
        preview = DraftClaimClusterPreview(
            workflow_run_id=workflow_run_id,
            groups=groups,
            created_at=created_at,
            updated_at=created_at,
        )
        return await self.cluster_preview_repository.save_preview(preview)


def _preview_groups_from_nodes(
    compacted_nodes: Sequence[DraftClaimCompactionNode],
) -> tuple[DraftClaimClusterPreviewGroup, ...]:
    claims_by_group: dict[str, list[DraftClaimClusterPreviewClaim]] = {}
    for node in compacted_nodes:
        group_ref = _node_text(node, "group_ref")
        claims_by_group.setdefault(group_ref, []).append(_preview_claim_from_node(node))

    return tuple(
        DraftClaimClusterPreviewGroup(
            group_ref=group_ref,
            claims=tuple(claims),
        )
        for group_ref, claims in sorted(
            claims_by_group.items(), key=lambda item: item[0]
        )
    )


def _preview_claim_from_node(
    node: DraftClaimCompactionNode,
) -> DraftClaimClusterPreviewClaim:
    payload = _node_payload(node)
    return DraftClaimClusterPreviewClaim(
        key=_node_text_or_payload(node, payload, "key", "compacted_key"),
        claim=_node_text_or_payload(node, payload, "claim", "compacted_claim"),
        claim_kind=_node_optional_text_or_payload(node, payload, "claim_kind"),
        granularity=_node_optional_text_or_payload(node, payload, "granularity"),
        source_claim_refs=_node_text_tuple_or_payload(
            node, payload, "source_claim_refs"
        ),
        triples=_node_json_object_tuple_or_payload(
            node,
            payload,
            "triples",
            "compacted_triples",
        ),
        possible_questions=_node_text_tuple_or_payload(
            node,
            payload,
            "possible_questions",
        ),
        exclusion_scope=_node_text_allow_empty_or_payload(
            node,
            payload,
            "exclusion_scope",
        ),
        evidence_block=_node_text_or_payload(
            node,
            payload,
            "evidence_block",
        ),
    )


def _node_payload(node: object) -> Mapping[str, object]:
    for attr_name in (
        "preview_payload",
        "payload",
        "claim_payload",
        "compacted_claim_payload",
    ):
        value = _node_attr(node, attr_name)
        if isinstance(value, Mapping):
            return value
    if isinstance(node, Mapping):
        for key in (
            "preview_payload",
            "payload",
            "claim_payload",
            "compacted_claim_payload",
        ):
            value = node.get(key)
            if isinstance(value, Mapping):
                return value
    return {}


def _node_text_allow_empty_or_payload(
    node: object,
    payload: Mapping[str, object],
    key: str,
) -> str:
    value = _node_attr(node, key)
    if isinstance(value, str):
        return value
    payload_value = payload.get(key)
    if isinstance(payload_value, str):
        return payload_value
    return ""


def _node_text_or_payload(
    node: object,
    payload: Mapping[str, object],
    *keys: str,
) -> str:
    for key in keys:
        value = _node_attr(node, key)
        if isinstance(value, str) and value.strip():
            return value
        payload_value = payload.get(key)
        if isinstance(payload_value, str) and payload_value.strip():
            return payload_value
    raise DraftClaimClusterPreviewBuildError(
        f"compacted node lacks required text field {keys[0]}"
    )


def _node_optional_text_or_payload(
    node: object,
    payload: Mapping[str, object],
    key: str,
) -> str | None:
    value = _node_attr(node, key)
    if isinstance(value, str) and value.strip():
        return value
    payload_value = payload.get(key)
    if isinstance(payload_value, str) and payload_value.strip():
        return payload_value
    return None


def _node_text_tuple_or_payload(
    node: object,
    payload: Mapping[str, object],
    key: str,
) -> tuple[str, ...]:
    value = _node_attr(node, key)
    if isinstance(value, tuple) and all(isinstance(item, str) for item in value):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return tuple(value)
    payload_value = payload.get(key)
    if isinstance(payload_value, list) and all(
        isinstance(item, str) for item in payload_value
    ):
        return tuple(payload_value)
    return ()


def _node_json_object_tuple_or_payload(
    node: object,
    payload: Mapping[str, object],
    *keys: str,
) -> tuple[JsonObject, ...]:
    for key in keys:
        value = _node_attr(node, key)
        if isinstance(value, tuple):
            return tuple(_json_object(item) for item in value)
        if isinstance(value, list):
            return tuple(_json_object(item) for item in value)
        payload_value = payload.get(key)
        if isinstance(payload_value, list):
            return tuple(_json_object(item) for item in payload_value)
    return ()


def _node_text(node: object, key: str) -> str:
    value = _node_attr(node, key)
    if isinstance(value, str) and value.strip():
        return value
    raise DraftClaimClusterPreviewBuildError(f"compacted node lacks {key}")


def _node_attr(node: object, key: str) -> object:
    if isinstance(node, Mapping):
        return node.get(key)
    return getattr(node, key, None)


def _json_object(value: object) -> JsonObject:
    if not isinstance(value, Mapping):
        raise DraftClaimClusterPreviewBuildError("triple must be object")
    result: JsonObject = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise DraftClaimClusterPreviewBuildError("triple keys must be str")
        result[key] = _json_value(item)
    return result


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float):
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return _json_object(value)
    raise DraftClaimClusterPreviewBuildError("value must be JSON-compatible")
