from __future__ import annotations

from dataclasses import dataclass

from .shared import (
    DocumentId,
    DomainInvariantError,
    JsonValue,
    NodeRunId,
    ProjectId,
    SectionId,
    require_document_id,
    require_node_run_id,
    require_project_id,
)


@dataclass(frozen=True, slots=True)
class LocalClaimTriple:
    subject: str
    predicate: str
    object: str
    qualifiers: tuple[JsonValue, ...] = ()

    def __post_init__(self) -> None:
        if not self.subject.strip():
            raise DomainInvariantError("local claim triple subject is required")
        if not self.predicate.strip():
            raise DomainInvariantError("local claim triple predicate is required")
        if not self.object.strip():
            raise DomainInvariantError("local claim triple object is required")


@dataclass(frozen=True, slots=True)
class LocalEvidenceMention:
    evidence_block: str
    source_refs: tuple[str, ...] = ()
    source_chunk_indexes: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not self.evidence_block.strip():
            raise DomainInvariantError("local evidence mention evidence_block is required")


@dataclass(frozen=True, slots=True)
class LocalClaimRelation:
    target_ref: str
    relation: str
    reason: str

    def __post_init__(self) -> None:
        if not self.target_ref.strip():
            raise DomainInvariantError("local claim relation target_ref is required")
        if not self.relation.strip():
            raise DomainInvariantError("local claim relation type is required")
        if not self.reason.strip():
            raise DomainInvariantError("local claim relation reason is required")


@dataclass(frozen=True, slots=True)
class LocalClaim:
    local_ref: str
    claim: str
    claim_kind: str
    granularity: str
    triples: tuple[LocalClaimTriple, ...]
    evidence: LocalEvidenceMention
    possible_questions: tuple[str, ...]
    scope: str
    exclusion_scope: str
    local_relations: tuple[LocalClaimRelation, ...] = ()
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if not self.local_ref.strip():
            raise DomainInvariantError("local claim local_ref is required")
        if not self.claim.strip():
            raise DomainInvariantError("local claim text is required")
        if not self.claim_kind.strip():
            raise DomainInvariantError("local claim_kind is required")
        if self.granularity not in {"atomic", "composite"}:
            raise DomainInvariantError("local claim granularity must be atomic or composite")
        if not self.triples:
            raise DomainInvariantError("local claim requires triples")
        if not 0 <= self.confidence <= 1:
            raise DomainInvariantError("local claim confidence must be in [0, 1]")


@dataclass(frozen=True, slots=True)
class LocalClaimGraph:
    project_id: ProjectId
    document_id: DocumentId
    section_id: SectionId
    node_run_id: NodeRunId
    claims: tuple[LocalClaim, ...]

    def __post_init__(self) -> None:
        require_project_id(self.project_id)
        require_document_id(self.document_id)
        require_node_run_id(self.node_run_id)
        if not str(self.section_id).strip():
            raise DomainInvariantError("local claim graph section_id is required")
        if not self.claims:
            raise DomainInvariantError("local claim graph requires non-empty claim_observations")


def local_claim_graph_from_claim_observations_payload(
    payload: JsonValue,
    *,
    project_id: ProjectId,
    document_id: DocumentId,
    section_id: SectionId,
    node_run_id: NodeRunId,
) -> LocalClaimGraph:
    if not isinstance(payload, dict):
        raise DomainInvariantError("local claim graph payload must be object")

    raw_claims = payload.get("claim_observations")
    if not isinstance(raw_claims, list) or not raw_claims:
        raise DomainInvariantError("local claim graph requires non-empty claim_observations")

    claims: list[LocalClaim] = []
    for index, raw_claim in enumerate(raw_claims):
        if not isinstance(raw_claim, dict):
            raise DomainInvariantError(f"local claim #{index} must be object")
        _reject_later_stage_keys(raw_claim, index=index)
        claims.append(_parse_local_claim(raw_claim, index=index))

    return LocalClaimGraph(
        project_id=project_id,
        document_id=document_id,
        section_id=section_id,
        node_run_id=node_run_id,
        claims=tuple(claims),
    )


def _reject_later_stage_keys(payload: dict[str, JsonValue], *, index: int) -> None:
    forbidden = {
        "relation_to_" + "known_claim",
        "suggested_" + "registry_action",
        "known_claim_id",
        "registry_action",
    }
    present = sorted(forbidden.intersection(payload))
    if present:
        raise DomainInvariantError(
            f"local claim #{index} contains later-stage fields forbidden in Prompt A: "
            + ", ".join(present)
        )


def _parse_local_claim(payload: dict[str, JsonValue], *, index: int) -> LocalClaim:
    return LocalClaim(
        local_ref=_required_str(payload, "local_ref", index=index),
        claim=_required_str(payload, "claim", index=index),
        claim_kind=_required_str(payload, "claim_kind", index=index),
        granularity=_required_str(payload, "granularity", index=index),
        triples=tuple(
            _parse_triple(item, claim_index=index, triple_index=triple_index)
            for triple_index, item in enumerate(
                _required_list(payload, "triples", index=index)
            )
        ),
        evidence=LocalEvidenceMention(
            evidence_block=_required_str(payload, "evidence_block", index=index),
            source_refs=_string_tuple(payload.get("source_refs"), key="source_refs"),
            source_chunk_indexes=_int_tuple(
                payload.get("source_chunk_indexes"),
                key="source_chunk_indexes",
            ),
        ),
        possible_questions=_string_tuple(
            payload.get("possible_questions"),
            key="possible_questions",
        ),
        scope=_optional_str(payload, "scope") or "",
        exclusion_scope=_optional_str(payload, "exclusion_scope") or "",
        local_relations=tuple(
            _parse_local_relation(item, claim_index=index, relation_index=relation_index)
            for relation_index, item in enumerate(
                _required_list(payload, "local_relations", index=index, allow_empty=True)
            )
        ),
        confidence=_float(payload.get("confidence"), key="confidence"),
    )


def _parse_local_relation(
    value: JsonValue,
    *,
    claim_index: int,
    relation_index: int,
) -> LocalClaimRelation:
    if not isinstance(value, dict):
        raise DomainInvariantError(
            f"local claim #{claim_index} relation #{relation_index} must be object"
        )
    return LocalClaimRelation(
        target_ref=_required_str(value, "target_ref", index=claim_index),
        relation=_required_str(value, "relation", index=claim_index),
        reason=_required_str(value, "reason", index=claim_index),
    )


def _parse_triple(
    value: JsonValue,
    *,
    claim_index: int,
    triple_index: int,
) -> LocalClaimTriple:
    if not isinstance(value, dict):
        raise DomainInvariantError(
            f"local claim #{claim_index} triple #{triple_index} must be object"
        )
    return LocalClaimTriple(
        subject=_required_str(value, "subject", index=claim_index),
        predicate=_required_str(value, "predicate", index=claim_index),
        object=_required_str(value, "object", index=claim_index),
        qualifiers=tuple(
            _required_list(value, "qualifiers", index=claim_index, allow_empty=True)
        ),
    )


def _required_str(payload: dict[str, JsonValue], key: str, *, index: int) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DomainInvariantError(f"local claim #{index} requires {key}")
    return value.strip()


def _optional_str(payload: dict[str, JsonValue], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise DomainInvariantError(f"{key} must be string")
    return value.strip()


def _required_list(
    payload: dict[str, JsonValue],
    key: str,
    *,
    index: int,
    allow_empty: bool = False,
) -> list[JsonValue]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise DomainInvariantError(f"local claim #{index} requires list {key}")
    if not value and not allow_empty:
        raise DomainInvariantError(f"local claim #{index} requires non-empty {key}")
    return value


def _string_tuple(value: JsonValue, *, key: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise DomainInvariantError(f"{key} must be list")
    result: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise DomainInvariantError(f"{key} items must be strings")
        normalized = item.strip()
        if normalized:
            result.append(normalized)
    return tuple(result)


def _int_tuple(value: JsonValue, *, key: str) -> tuple[int, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise DomainInvariantError(f"{key} must be list")
    result: list[int] = []
    for item in value:
        if not isinstance(item, int):
            raise DomainInvariantError(f"{key} items must be integers")
        result.append(item)
    return tuple(result)


def _float(value: JsonValue, *, key: str) -> float:
    if not isinstance(value, (int, float)):
        raise DomainInvariantError(f"{key} must be number")
    return float(value)


__all__ = [
    "LocalClaim",
    "LocalClaimGraph",
    "LocalClaimRelation",
    "LocalClaimTriple",
    "LocalEvidenceMention",
    "local_claim_graph_from_claim_observations_payload",
]
