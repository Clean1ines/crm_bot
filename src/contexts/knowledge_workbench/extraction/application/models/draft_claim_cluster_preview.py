from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from src.domain.project_plane.json_types import JsonObject, JsonValue


@dataclass(frozen=True, slots=True)
class DraftClaimClusterPreviewClaim:
    key: str
    claim: str
    claim_kind: str | None
    granularity: str | None
    source_claim_refs: tuple[str, ...]
    triples: tuple[JsonObject, ...]
    possible_questions: tuple[str, ...]
    exclusion_scope: str
    evidence_block: str

    def __post_init__(self) -> None:
        _require_non_empty_text(self.key, field_name="key")
        _require_non_empty_text(self.claim, field_name="claim")
        if self.claim_kind is not None:
            _require_non_empty_text(self.claim_kind, field_name="claim_kind")
        if self.granularity is not None:
            _require_non_empty_text(self.granularity, field_name="granularity")
        for source_claim_ref in self.source_claim_refs:
            _require_non_empty_text(source_claim_ref, field_name="source_claim_ref")
        for triple in self.triples:
            _require_json_object(triple, field_name="triple")
        for question in self.possible_questions:
            _require_non_empty_text(question, field_name="possible_question")
        if not isinstance(self.exclusion_scope, str):
            raise TypeError("exclusion_scope must be str")
        _require_non_empty_text(self.evidence_block, field_name="evidence_block")

    def to_payload(self) -> JsonObject:
        payload: JsonObject = {
            "key": self.key,
            "claim": self.claim,
            "claim_kind": self.claim_kind,
            "granularity": self.granularity,
            "source_claim_refs": list(self.source_claim_refs),
            "triples": [dict(triple) for triple in self.triples],
            "possible_questions": list(self.possible_questions),
            "exclusion_scope": self.exclusion_scope,
            "evidence_block": self.evidence_block,
        }
        return payload

    @classmethod
    def from_payload(
        cls, payload: Mapping[str, object]
    ) -> "DraftClaimClusterPreviewClaim":
        return cls(
            key=_payload_text(payload, "key"),
            claim=_payload_text(payload, "claim"),
            claim_kind=_payload_optional_text(payload, "claim_kind"),
            granularity=_payload_optional_text(payload, "granularity"),
            source_claim_refs=_payload_text_tuple(payload, "source_claim_refs"),
            triples=_payload_json_object_tuple(payload, "triples"),
            possible_questions=_payload_text_tuple(payload, "possible_questions"),
            exclusion_scope=_payload_text_allow_empty(payload, "exclusion_scope"),
            evidence_block=_payload_text(payload, "evidence_block"),
        )


@dataclass(frozen=True, slots=True)
class DraftClaimClusterPreviewGroup:
    group_ref: str
    claims: tuple[DraftClaimClusterPreviewClaim, ...]

    def __post_init__(self) -> None:
        _require_non_empty_text(self.group_ref, field_name="group_ref")
        if not self.claims:
            raise ValueError("preview group claims must be non-empty")

    def to_payload(self) -> JsonObject:
        return {
            "group_ref": self.group_ref,
            "claims": [claim.to_payload() for claim in self.claims],
        }

    @classmethod
    def from_payload(
        cls, payload: Mapping[str, object]
    ) -> "DraftClaimClusterPreviewGroup":
        claims_value = payload.get("claims")
        if not isinstance(claims_value, list):
            raise ValueError("preview group claims must be list")
        claims = tuple(
            DraftClaimClusterPreviewClaim.from_payload(_payload_mapping(item, "claim"))
            for item in claims_value
        )
        return cls(
            group_ref=_payload_text(payload, "group_ref"),
            claims=claims,
        )


@dataclass(frozen=True, slots=True)
class DraftClaimClusterPreview:
    workflow_run_id: str
    groups: tuple[DraftClaimClusterPreviewGroup, ...]
    created_at: datetime
    updated_at: datetime

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        if not self.groups:
            raise ValueError("preview groups must be non-empty")

    @property
    def claim_count(self) -> int:
        return sum(len(group.claims) for group in self.groups)

    @property
    def group_count(self) -> int:
        return len(self.groups)

    def to_payload(self) -> JsonObject:
        return {
            "workflow_run_id": self.workflow_run_id,
            "groups": [group.to_payload() for group in self.groups],
            "claim_count": self.claim_count,
            "group_count": self.group_count,
        }

    @classmethod
    def from_payload(
        cls,
        *,
        workflow_run_id: str,
        payload: Mapping[str, object],
        created_at: datetime,
        updated_at: datetime,
    ) -> "DraftClaimClusterPreview":
        groups_value = payload.get("groups")
        if not isinstance(groups_value, list):
            raise ValueError("preview groups must be list")
        groups = tuple(
            DraftClaimClusterPreviewGroup.from_payload(_payload_mapping(item, "group"))
            for item in groups_value
        )
        return cls(
            workflow_run_id=workflow_run_id,
            groups=groups,
            created_at=created_at,
            updated_at=updated_at,
        )


@dataclass(frozen=True, slots=True)
class DraftClaimClusterPreviewBuildResult:
    workflow_run_id: str
    claim_count: int
    group_count: int
    created_preview: bool
    updated_preview: bool

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        if self.claim_count <= 0:
            raise ValueError("claim_count must be > 0")
        if self.group_count <= 0:
            raise ValueError("group_count must be > 0")


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_json_object(value: Mapping[str, object], *, field_name: str) -> None:
    for key in value:
        if not isinstance(key, str):
            raise ValueError(f"{field_name} keys must be str")


def _payload_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"payload {key} must be non-empty str")
    return value


def _payload_text_allow_empty(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"payload {key} must be str")
    return value


def _payload_optional_text(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"payload {key} must be non-empty str when set")
    return value


def _payload_text_tuple(payload: Mapping[str, object], key: str) -> tuple[str, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"payload {key} must be list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"payload {key} must contain non-empty strings")
        result.append(item)
    return tuple(result)


def _payload_json_object_tuple(
    payload: Mapping[str, object],
    key: str,
) -> tuple[JsonObject, ...]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"payload {key} must be list")
    return tuple(_json_object(item, key) for item in value)


def _payload_mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be object")
    return value


def _json_object(value: object, field_name: str) -> JsonObject:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} item must be object")
    result: JsonObject = {}
    for key, item in value.items():
        if not isinstance(key, str):
            raise ValueError(f"{field_name} item keys must be str")
        result[key] = _json_value(item)
    return result


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, str | int | float):
        return value
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, Mapping):
        return _json_object(value, "mapping")
    raise ValueError("value must be JSON-compatible")
