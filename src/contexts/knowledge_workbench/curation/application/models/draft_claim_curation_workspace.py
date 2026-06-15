from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from src.contexts.knowledge_workbench.extraction.application.models.draft_claim_compaction_prompt_contract import (
    DraftClaimCompactionClaimKind,
    DraftClaimCompactionGranularity,
    DraftClaimCompactionMergeDecision,
    DraftClaimCompactionTriplePredicate,
)
from src.domain.project_plane.json_types import JsonObject, JsonValue


class DraftClaimCurationWorkspaceStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"


@dataclass(frozen=True, slots=True)
class DraftClaimCurationItemEditablePayload:
    payload: JsonObject

    def __post_init__(self) -> None:
        normalized = _validated_publishable_payload(self.payload)
        object.__setattr__(self, "payload", normalized)

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, object],
    ) -> "DraftClaimCurationItemEditablePayload":
        return cls(payload=_json_object(payload))

    def to_json_dict(self) -> JsonObject:
        return dict(self.payload)

    @property
    def source_claim_refs(self) -> tuple[str, ...]:
        return tuple(_payload_text_list(self.payload, "source_claim_refs"))

    def with_editable_updates(
        self,
        updates: Mapping[str, object],
    ) -> "DraftClaimCurationItemEditablePayload":
        forbidden = {
            "source_claim_refs",
            "original_payload",
            "compacted_node_ref",
            "workflow_run_id",
            "workspace_ref",
            "merge_decision",
        }
        unknown = (
            set(updates)
            - {
                "key",
                "claim",
                "claim_kind",
                "granularity",
                "triples",
                "possible_questions",
                "exclusion_scope",
                "evidence_block",
            }
            - forbidden
        )
        if unknown:
            raise ValueError(f"unknown editable payload fields: {sorted(unknown)}")
        blocked = set(updates) & forbidden
        if blocked:
            raise ValueError(f"non-editable payload fields: {sorted(blocked)}")

        mutable = dict(self.payload)
        for key, value in updates.items():
            if key == "possible_questions":
                mutable[key] = list(_dedupe_stripped(_object_text_list(value, key)))
            elif key == "triples":
                mutable[key] = [
                    _triple_object(item) for item in _object_list(value, key)
                ]
            elif key in {"key", "claim", "claim_kind", "granularity", "evidence_block"}:
                mutable[key] = _object_required_text(value, key)
            elif key == "exclusion_scope":
                mutable[key] = _object_text(value, key)
        return DraftClaimCurationItemEditablePayload(payload=_json_object(mutable))


@dataclass(frozen=True, slots=True)
class DraftClaimCurationWorkspace:
    workspace_ref: str
    workflow_run_id: str
    project_id: str | None
    source_document_ref: str | None
    status: DraftClaimCurationWorkspaceStatus
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.workspace_ref, "workspace_ref")
        _require_text(self.workflow_run_id, "workflow_run_id")
        _require_optional_text(self.project_id, "project_id")
        _require_optional_text(self.source_document_ref, "source_document_ref")
        object.__setattr__(
            self,
            "status",
            DraftClaimCurationWorkspaceStatus(self.status),
        )
        _require_datetime(self.created_at, "created_at")
        _require_datetime(self.updated_at, "updated_at")

    def to_json_dict(self) -> JsonObject:
        return {
            "workspace_ref": self.workspace_ref,
            "workflow_run_id": self.workflow_run_id,
            "project_id": self.project_id,
            "source_document_ref": self.source_document_ref,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class DraftClaimCurationWorkspaceItem:
    item_ref: str
    workspace_ref: str
    workflow_run_id: str
    group_ref: str
    compacted_node_ref: str
    source_claim_refs: tuple[str, ...]
    original_payload: DraftClaimCurationItemEditablePayload
    editable_payload: DraftClaimCurationItemEditablePayload
    excluded: bool
    exclusion_reason: str | None
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _require_text(self.item_ref, "item_ref")
        _require_text(self.workspace_ref, "workspace_ref")
        _require_text(self.workflow_run_id, "workflow_run_id")
        _require_text(self.group_ref, "group_ref")
        _require_text(self.compacted_node_ref, "compacted_node_ref")
        _require_text_tuple(self.source_claim_refs, "source_claim_refs")
        if self.source_claim_refs != self.original_payload.source_claim_refs:
            raise ValueError("item source_claim_refs must match original_payload")
        if self.source_claim_refs != self.editable_payload.source_claim_refs:
            raise ValueError("item source_claim_refs must match editable_payload")
        if not isinstance(self.excluded, bool):
            raise TypeError("excluded must be bool")
        _require_optional_text(self.exclusion_reason, "exclusion_reason")
        _require_datetime(self.created_at, "created_at")
        _require_datetime(self.updated_at, "updated_at")

    def to_json_dict(self) -> JsonObject:
        return {
            "item_ref": self.item_ref,
            "workspace_ref": self.workspace_ref,
            "workflow_run_id": self.workflow_run_id,
            "group_ref": self.group_ref,
            "compacted_node_ref": self.compacted_node_ref,
            "source_claim_refs": list(self.source_claim_refs),
            "original_payload": self.original_payload.to_json_dict(),
            "editable_payload": self.editable_payload.to_json_dict(),
            "excluded": self.excluded,
            "exclusion_reason": self.exclusion_reason,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class DraftClaimCurationWorkspaceSnapshot:
    workspace: DraftClaimCurationWorkspace
    items: tuple[DraftClaimCurationWorkspaceItem, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.workspace, DraftClaimCurationWorkspace):
            raise TypeError("workspace must be DraftClaimCurationWorkspace")
        if not isinstance(self.items, tuple):
            raise TypeError("items must be tuple")
        for item in self.items:
            if not isinstance(item, DraftClaimCurationWorkspaceItem):
                raise TypeError("items must contain DraftClaimCurationWorkspaceItem")
            if item.workspace_ref != self.workspace.workspace_ref:
                raise ValueError("item workspace_ref must match workspace")

    def to_json_dict(self) -> JsonObject:
        return {
            "workspace": self.workspace.to_json_dict(),
            "items": [item.to_json_dict() for item in self.items],
        }


def draft_claim_curation_workspace_ref(workflow_run_id: str) -> str:
    _require_text(workflow_run_id, "workflow_run_id")
    return f"draft-claim-curation-workspace:{workflow_run_id}"


def draft_claim_curation_item_ref(
    *, workspace_ref: str, compacted_node_ref: str
) -> str:
    _require_text(workspace_ref, "workspace_ref")
    _require_text(compacted_node_ref, "compacted_node_ref")
    return f"draft-claim-curation-item:{workspace_ref}:{compacted_node_ref}"


def _validated_publishable_payload(payload: Mapping[str, object]) -> JsonObject:
    allowed = {
        "key",
        "claim",
        "claim_kind",
        "granularity",
        "source_claim_refs",
        "triples",
        "merge_decision",
        "possible_questions",
        "exclusion_scope",
        "evidence_block",
    }
    missing = allowed - set(payload)
    if missing:
        raise ValueError(f"publishable payload missing fields: {sorted(missing)}")
    extra = set(payload) - allowed
    if extra:
        raise ValueError(f"publishable payload unknown fields: {sorted(extra)}")

    normalized: JsonObject = {
        "key": _payload_required_text(payload, "key"),
        "claim": _payload_required_text(payload, "claim"),
        "claim_kind": DraftClaimCompactionClaimKind(
            _payload_required_text(payload, "claim_kind")
        ).value,
        "granularity": DraftClaimCompactionGranularity(
            _payload_required_text(payload, "granularity")
        ).value,
        "source_claim_refs": _payload_json_text_list(payload, "source_claim_refs"),
        "triples": _payload_triples(payload),
        "merge_decision": DraftClaimCompactionMergeDecision(
            _payload_required_text(payload, "merge_decision")
        ).value,
        "possible_questions": _payload_deduped_json_text_list(
            payload, "possible_questions"
        ),
        "exclusion_scope": _payload_text(payload, "exclusion_scope"),
        "evidence_block": _payload_required_text(payload, "evidence_block"),
    }
    return normalized


def _payload_json_text_list(
    payload: Mapping[str, object],
    key: str,
) -> list[JsonValue]:
    return _json_text_list(_payload_text_list(payload, key))


def _payload_deduped_json_text_list(
    payload: Mapping[str, object],
    key: str,
) -> list[JsonValue]:
    return _json_text_list(list(_dedupe_stripped(_payload_text_list(payload, key))))


def _object_json_text_list(value: object, key: str) -> list[JsonValue]:
    return _json_text_list(_object_text_list(value, key))


def _json_text_list(values: list[str]) -> list[JsonValue]:
    result: list[JsonValue] = []
    result.extend(values)
    return result


def _payload_triples(payload: Mapping[str, object]) -> list[JsonValue]:
    value = payload.get("triples")
    triples = _object_list(value, "triples")
    return [_triple_object(item) for item in triples]


def _triple_object(value: object) -> JsonObject:
    if not isinstance(value, Mapping):
        raise TypeError("triple must be object")
    allowed = {"subject", "predicate", "object", "qualifiers"}
    missing = {"subject", "predicate", "object"} - set(value)
    if missing:
        raise ValueError(f"triple missing fields: {sorted(missing)}")
    extra = set(value) - allowed
    if extra:
        raise ValueError(f"triple unknown fields: {sorted(extra)}")
    qualifiers_value = value.get("qualifiers", [])
    return {
        "subject": _payload_required_text(value, "subject"),
        "predicate": DraftClaimCompactionTriplePredicate(
            _payload_required_text(value, "predicate")
        ).value,
        "object": _payload_required_text(value, "object"),
        "qualifiers": _object_json_text_list(qualifiers_value, "qualifiers"),
    }


def _payload_required_text(payload: Mapping[str, object], key: str) -> str:
    return _object_required_text(payload.get(key), key)


def _payload_text(payload: Mapping[str, object], key: str) -> str:
    return _object_text(payload.get(key), key)


def _payload_text_list(payload: Mapping[str, object], key: str) -> list[str]:
    return _object_text_list(payload.get(key), key)


def _object_text(value: object, key: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{key} must be str")
    return value.strip()


def _object_required_text(value: object, key: str) -> str:
    text = _object_text(value, key)
    if not text:
        raise ValueError(f"{key} must be non-empty")
    return text


def _object_list(value: object, key: str) -> list[object]:
    if not isinstance(value, list):
        raise TypeError(f"{key} must be list")
    return list(value)


def _object_text_list(value: object, key: str) -> list[str]:
    items = _object_list(value, key)
    result: list[str] = []
    for item in items:
        if not isinstance(item, str):
            raise TypeError(f"{key} must contain strings")
        result.append(item.strip())
    return result


def _dedupe_stripped(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        stripped = value.strip()
        if not stripped:
            continue
        if stripped in seen:
            continue
        seen.add(stripped)
        result.append(stripped)
    return tuple(result)


def _json_object(value: Mapping[str, object]) -> JsonObject:
    result: JsonObject = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise TypeError("JSON object keys must be str")
        result[key] = _json_value(item)
    return result


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return _json_object(value)
    raise TypeError("value must be JSON-compatible")


def _require_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty str")


def _require_optional_text(value: str | None, field_name: str) -> None:
    if value is None:
        return
    _require_text(value, field_name)


def _require_text_tuple(values: tuple[str, ...], field_name: str) -> None:
    if not isinstance(values, tuple) or not values:
        raise ValueError(f"{field_name} must be non-empty tuple")
    if len(set(values)) != len(values):
        raise ValueError(f"{field_name} must be unique")
    for value in values:
        _require_text(value, field_name)


def _require_datetime(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
