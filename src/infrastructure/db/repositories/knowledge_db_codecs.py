from __future__ import annotations

import json
from collections.abc import Mapping, Sequence

from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.knowledge_compilation import (
    CanonicalKnowledgeEntry,
    SourceRef,
)
from src.domain.project_plane.knowledge_views import SourceRefView


def normalize_timestamp(value: object) -> str | None:
    """
    Keep test strings unchanged and serialize real datetime-like values only
    when the repository owns the DB-row normalization boundary.
    """
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if hasattr(value, "isoformat"):
        return str(value.isoformat())
    return str(value)


def jsonb_object_payload(value: Mapping[str, object]) -> str:
    return json.dumps(dict(value), ensure_ascii=False, default=str)


def pg_vector_text(embedding: list[float]) -> str:
    return "[" + ",".join(str(x) for x in embedding) + "]"


def json_object_from_db(value: object) -> JsonObject:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    if isinstance(value, str) and value.strip():
        parsed = json.loads(value)
        if isinstance(parsed, Mapping):
            return {str(key): item for key, item in parsed.items()}
    return {}


def json_list_from_db(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str) and value.strip():
        parsed = json.loads(value)
        if isinstance(parsed, list):
            return parsed
    return []


def optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str) and value.strip().isdigit():
        return int(value.strip())
    return None


def optional_float(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int | float | str):
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
    return None


def text_tuple_from_json(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        values: Sequence[object] = (value,)
    elif isinstance(value, Sequence) and not isinstance(value, bytes | bytearray):
        values = value
    else:
        return ()

    result: list[str] = []
    for item in values:
        cleaned = " ".join(str(item or "").strip().split())
        if cleaned and cleaned not in result:
            result.append(cleaned)
    return tuple(result)


def source_ref_from_mapping(payload: Mapping[str, object]) -> SourceRef:
    source_chunk_value = payload.get("source_chunk_id")
    return SourceRef(
        source_index=optional_int(payload.get("source_index")),
        quote=" ".join(str(payload.get("quote") or "").strip().split()),
        source_chunk_id=str(source_chunk_value) if source_chunk_value else None,
        start_offset=optional_int(payload.get("start_offset")),
        end_offset=optional_int(payload.get("end_offset")),
        confidence=optional_float(payload.get("confidence")),
    )


def source_refs_from_db(value: object) -> tuple[SourceRef, ...]:
    refs: list[SourceRef] = []
    for item in json_list_from_db(value):
        if not isinstance(item, Mapping):
            continue
        ref = source_ref_from_mapping(item)
        if ref.quote:
            refs.append(ref)
    return tuple(refs)


def source_ref_payload(ref: SourceRef) -> dict[str, object]:
    payload: dict[str, object] = {"quote": ref.quote}
    if ref.source_index is not None:
        payload["source_index"] = ref.source_index
    if ref.source_chunk_id is not None:
        payload["source_chunk_id"] = ref.source_chunk_id
    if ref.start_offset is not None:
        payload["start_offset"] = ref.start_offset
    if ref.end_offset is not None:
        payload["end_offset"] = ref.end_offset
    if ref.confidence is not None:
        payload["confidence"] = ref.confidence
    return payload


def source_refs_payload(entry: CanonicalKnowledgeEntry) -> list[dict[str, object]]:
    return [source_ref_payload(ref) for ref in entry.source_refs]


def source_ref_view_from_mapping(payload: Mapping[str, object]) -> SourceRefView:
    quote = " ".join(str(payload.get("quote") or "").strip().split())
    source_chunk_id_value = payload.get("source_chunk_id")
    return SourceRefView(
        source_index=optional_int(payload.get("source_index")),
        quote=quote,
        source_chunk_id=str(source_chunk_id_value) if source_chunk_id_value else None,
        start_offset=optional_int(payload.get("start_offset")),
        end_offset=optional_int(payload.get("end_offset")),
        confidence=optional_float(payload.get("confidence")),
    )


def source_ref_views_from_payload(value: object) -> tuple[SourceRefView, ...]:
    if not isinstance(value, list):
        return ()

    refs: list[SourceRefView] = []
    for item in value:
        if isinstance(item, Mapping):
            ref = source_ref_view_from_mapping(item)
            if ref.quote:
                refs.append(ref)
    return tuple(refs)


def first_source_excerpt(source_refs: tuple[SourceRefView, ...]) -> str | None:
    for source_ref in source_refs:
        if source_ref.quote:
            return source_ref.quote
    return None
