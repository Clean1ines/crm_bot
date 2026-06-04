from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol

from src.domain.project_plane.knowledge_workbench import (
    DomainInvariantError,
    JsonValue,
    RegistrySnapshot,
)


class RegistryMaterializationRepositoryPort(Protocol):
    async def replace_canonical_facts_for_snapshot(
        self,
        *,
        snapshot: RegistrySnapshot,
        canonical_facts: tuple[Mapping[str, object], ...],
    ) -> int: ...

    async def replace_fact_mentions_for_snapshot(
        self,
        *,
        snapshot: RegistrySnapshot,
        fact_mentions: tuple[Mapping[str, object], ...],
    ) -> int: ...

    async def replace_fact_relations_for_snapshot(
        self,
        *,
        snapshot: RegistrySnapshot,
        fact_relations: tuple[Mapping[str, object], ...],
    ) -> int: ...

    async def replace_surfaces_for_snapshot(
        self,
        *,
        snapshot: RegistrySnapshot,
        surfaces: tuple[Mapping[str, object], ...],
    ) -> int: ...


@dataclass(frozen=True, slots=True)
class MaterializeFactRegistrySnapshotCommand:
    snapshot: RegistrySnapshot


@dataclass(frozen=True, slots=True)
class MaterializeFactRegistrySnapshotResult:
    canonical_fact_count: int
    fact_mention_count: int
    fact_relation_count: int
    surface_count: int


class FaqWorkbenchRegistryMaterializationService:
    """Materialize final Prompt C fact_registry snapshot into first-class tables."""

    def __init__(
        self,
        repository: RegistryMaterializationRepositoryPort,
    ) -> None:
        self._repository = repository

    async def materialize_fact_registry_snapshot(
        self,
        command: MaterializeFactRegistrySnapshotCommand,
    ) -> MaterializeFactRegistrySnapshotResult:
        snapshot = command.snapshot
        fact_registry = _fact_registry_from_snapshot(snapshot)
        raw_facts = _object_list(fact_registry.get("canonical_facts"))
        raw_relations = _object_list(fact_registry.get("fact_relations"))

        canonical_facts = tuple(
            fact
            for raw_fact in raw_facts
            if (fact := _canonical_fact_row(snapshot, raw_fact)) is not None
        )
        fact_mentions = tuple(
            mention
            for raw_fact in raw_facts
            for mention in _fact_mention_rows(snapshot, raw_fact)
        )
        fact_relations = tuple(
            relation
            for index, raw_relation in enumerate(raw_relations, start=1)
            if (
                relation := _fact_relation_row(
                    snapshot=snapshot,
                    raw_relation=raw_relation,
                    index=index,
                )
            )
            is not None
        )
        surfaces = tuple(_surface_row(snapshot, fact) for fact in canonical_facts)

        canonical_fact_count = (
            await self._repository.replace_canonical_facts_for_snapshot(
                snapshot=snapshot,
                canonical_facts=canonical_facts,
            )
        )
        fact_mention_count = await self._repository.replace_fact_mentions_for_snapshot(
            snapshot=snapshot,
            fact_mentions=fact_mentions,
        )
        fact_relation_count = (
            await self._repository.replace_fact_relations_for_snapshot(
                snapshot=snapshot,
                fact_relations=fact_relations,
            )
        )
        surface_count = await self._repository.replace_surfaces_for_snapshot(
            snapshot=snapshot,
            surfaces=surfaces,
        )

        return MaterializeFactRegistrySnapshotResult(
            canonical_fact_count=canonical_fact_count,
            fact_mention_count=fact_mention_count,
            fact_relation_count=fact_relation_count,
            surface_count=surface_count,
        )


def _fact_registry_from_snapshot(snapshot: RegistrySnapshot) -> Mapping[str, object]:
    entries_payload = snapshot.entries_payload
    if not isinstance(entries_payload, Mapping):
        raise DomainInvariantError(
            "registry materialization requires object entries_payload"
        )

    fact_registry = entries_payload.get("fact_registry")
    if not isinstance(fact_registry, Mapping):
        raise DomainInvariantError(
            "registry materialization requires fact_registry payload"
        )

    return fact_registry


def _canonical_fact_row(
    snapshot: RegistrySnapshot,
    raw_fact: Mapping[str, object],
) -> Mapping[str, object] | None:
    fact_id = _clean_text(raw_fact.get("fact_id"))
    claim = _clean_text(raw_fact.get("claim"))
    status = _clean_text(raw_fact.get("status")) or "active"

    if not fact_id or not claim:
        return None
    if status == "deleted":
        return None

    question_variants = _text_tuple(raw_fact.get("question_variants"))
    answer = _clean_text(raw_fact.get("answer")) or claim
    scope = (
        _clean_text(raw_fact.get("scope"))
        or _clean_text(raw_fact.get("answer_scope"))
        or _clean_text(raw_fact.get("retrieval_scope"))
    )

    return {
        "fact_id": fact_id,
        "registry_id": snapshot.registry_id,
        "project_id": snapshot.project_id,
        "document_id": snapshot.document_id,
        "processing_run_id": snapshot.processing_run_id,
        "claim": claim,
        "claim_kind": _clean_text(raw_fact.get("claim_kind")) or "other",
        "granularity": _clean_text(raw_fact.get("granularity")) or "atomic",
        "possible_questions": question_variants,
        "scope": scope or answer,
        "exclusion_scope": _clean_text(raw_fact.get("exclusion_scope")),
        "derived_fact_notes": _json_list(raw_fact.get("derived_fact_notes")),
        "status": status,
        "answer": answer,
        "short_answer": _clean_text(raw_fact.get("short_answer")) or claim,
        "answer_scope": _clean_text(raw_fact.get("answer_scope")) or scope,
        "retrieval_scope": _clean_text(raw_fact.get("retrieval_scope")) or scope,
        "evidence_quotes": _evidence_quotes(raw_fact),
        "source_refs": _source_refs(raw_fact),
        "source_section_ids": _source_section_ids(raw_fact),
        "source_chunk_indexes": _source_chunk_indexes(raw_fact),
        "parent_fact_ids": _text_tuple(raw_fact.get("parent_fact_ids")),
        "child_fact_ids": _text_tuple(raw_fact.get("child_fact_ids")),
        "duplicate_fact_ids": _text_tuple(raw_fact.get("duplicate_fact_ids")),
        "overlap_fact_ids": _text_tuple(raw_fact.get("overlap_fact_ids")),
        "role_label_metadata": _json_object(raw_fact.get("metadata")),
    }


def _fact_mention_rows(
    snapshot: RegistrySnapshot,
    raw_fact: Mapping[str, object],
) -> tuple[Mapping[str, object], ...]:
    fact_id = _clean_text(raw_fact.get("fact_id"))
    if not fact_id:
        return ()

    rows: list[Mapping[str, object]] = []
    raw_mentions = _object_list(raw_fact.get("mentions"))
    for index, raw_mention in enumerate(raw_mentions, start=1):
        evidence_block = (
            _clean_text(raw_mention.get("evidence_block"))
            or _clean_text(raw_mention.get("evidence"))
            or _clean_text(raw_mention.get("quote"))
        )
        rows.append(
            {
                "mention_id": f"mention:{snapshot.snapshot_id}:{fact_id}:{index}",
                "fact_id": fact_id,
                "registry_id": snapshot.registry_id,
                "source_section_id": _clean_text_or_none(
                    raw_mention.get("source_section_id")
                ),
                "source_section_ref": _clean_text(raw_mention.get("source_section_ref"))
                or _clean_text(raw_mention.get("source_ref")),
                "source_local_ref": _clean_text(raw_mention.get("source_local_ref")),
                "evidence_block": evidence_block,
                "mention_relation": _clean_text(raw_mention.get("mention_relation"))
                or "supports",
            }
        )

    if rows:
        return tuple(rows)

    evidence_quotes = _evidence_quotes(raw_fact)
    source_refs = _source_refs(raw_fact)
    source_section_ids = _source_section_ids(raw_fact)

    for index, evidence_block in enumerate(evidence_quotes, start=1):
        source_ref = source_refs[index - 1] if index <= len(source_refs) else ""
        source_section_id = (
            source_section_ids[index - 1] if index <= len(source_section_ids) else None
        )
        rows.append(
            {
                "mention_id": f"mention:{snapshot.snapshot_id}:{fact_id}:{index}",
                "fact_id": fact_id,
                "registry_id": snapshot.registry_id,
                "source_section_id": source_section_id,
                "source_section_ref": source_ref,
                "source_local_ref": "",
                "evidence_block": evidence_block,
                "mention_relation": "supports",
            }
        )

    return tuple(rows)


def _fact_relation_row(
    *,
    snapshot: RegistrySnapshot,
    raw_relation: Mapping[str, object],
    index: int,
) -> Mapping[str, object] | None:
    source_fact_id = _clean_text(raw_relation.get("source_fact_id"))
    target_fact_id = _clean_text(raw_relation.get("target_fact_id"))
    relation = _clean_text(raw_relation.get("relation"))

    if not source_fact_id or not target_fact_id or not relation:
        return None
    if source_fact_id == target_fact_id:
        return None

    raw_relation_id = _clean_text(raw_relation.get("relation_id"))
    relation_id = raw_relation_id or f"relation:{snapshot.snapshot_id}:{index}"

    return {
        "relation_id": relation_id,
        "registry_id": snapshot.registry_id,
        "source_fact_id": source_fact_id,
        "target_fact_id": target_fact_id,
        "relation": relation,
        "reason": _clean_text(raw_relation.get("reason")),
    }


def _surface_row(
    snapshot: RegistrySnapshot,
    fact: Mapping[str, object],
) -> Mapping[str, object]:
    fact_id = str(fact["fact_id"])
    claim = str(fact["claim"])
    answer = str(fact["answer"])
    question_variants = _text_tuple(fact.get("possible_questions"))
    evidence_quotes = _text_tuple(fact.get("evidence_quotes"))
    source_refs = _text_tuple(fact.get("source_refs"))
    source_section_ids = _text_tuple(fact.get("source_section_ids"))

    return {
        "surface_id": f"surface:{snapshot.snapshot_id}:{fact_id}",
        "project_id": snapshot.project_id,
        "document_id": snapshot.document_id,
        "fact_id": fact_id,
        "title": claim,
        "claim": claim,
        "question_variants": question_variants,
        "answer": answer,
        "short_answer": str(fact.get("short_answer") or claim),
        "answer_scope": str(fact.get("answer_scope") or fact.get("scope") or ""),
        "retrieval_scope": str(fact.get("retrieval_scope") or fact.get("scope") or ""),
        "exclusion_scope": str(fact.get("exclusion_scope") or ""),
        "evidence_quotes": evidence_quotes,
        "source_refs": source_refs,
        "source_section_ids": source_section_ids,
        "claim_kind": str(fact.get("claim_kind") or "other"),
        "status": "ready",
        "curation_state": "auto_materialized",
    }


def _object_list(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _json_list(value: object) -> tuple[JsonValue, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()
    return tuple(_json_value(item) for item in value)


def _json_object(value: object) -> Mapping[str, JsonValue]:
    if not isinstance(value, Mapping):
        return {}
    return {str(key): _json_value(item) for key, item in value.items()}


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_json_value(item) for item in value]
    return str(value)


def _evidence_quotes(raw_fact: Mapping[str, object]) -> tuple[str, ...]:
    direct = _text_tuple(raw_fact.get("evidence_quotes"))
    if direct:
        return direct

    evidence = raw_fact.get("evidence")
    if isinstance(evidence, Sequence) and not isinstance(
        evidence, (str, bytes, bytearray)
    ):
        values: list[str] = []
        for item in evidence:
            if isinstance(item, Mapping):
                text = (
                    _clean_text(item.get("evidence_block"))
                    or _clean_text(item.get("quote"))
                    or _clean_text(item.get("text"))
                )
            else:
                text = _clean_text(item)
            if text:
                values.append(text)
        return tuple(dict.fromkeys(values))

    return ()


def _source_refs(raw_fact: Mapping[str, object]) -> tuple[str, ...]:
    direct = _text_tuple(raw_fact.get("source_refs"))
    if direct:
        return direct

    values: list[str] = []
    for item in _object_list(raw_fact.get("mentions")):
        for key in ("source_ref", "source_section_ref", "source_local_ref"):
            text = _clean_text(item.get(key))
            if text:
                values.append(text)

    return tuple(dict.fromkeys(values))


def _source_section_ids(raw_fact: Mapping[str, object]) -> tuple[str, ...]:
    values: list[str] = []
    for item in _object_list(raw_fact.get("mentions")):
        text = _clean_text(item.get("source_section_id"))
        if text:
            values.append(text)
    return tuple(dict.fromkeys(values))


def _source_chunk_indexes(raw_fact: Mapping[str, object]) -> tuple[int, ...]:
    value = raw_fact.get("source_chunk_indexes")
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return ()

    indexes: list[int] = []
    for item in value:
        if isinstance(item, int):
            indexes.append(item)
            continue
        text = str(item).strip()
        if text.isdigit():
            indexes.append(int(text))
    return tuple(indexes)


def _text_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        return (text,) if text else ()
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return tuple(text for item in value if (text := _clean_text(item)))
    text = _clean_text(value)
    return (text,) if text else ()


def _clean_text_or_none(value: object) -> str | None:
    text = _clean_text(value)
    return text or None


def _clean_text(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


__all__ = [
    "FaqWorkbenchRegistryMaterializationService",
    "MaterializeFactRegistrySnapshotCommand",
    "MaterializeFactRegistrySnapshotResult",
    "RegistryMaterializationRepositoryPort",
    "json_dumps",
]
