from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from datetime import datetime
from typing import cast

from src.domain.project_plane.knowledge_views import SourceRefView


def normalize_timestamp(value: object) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def jsonb_object_payload(value: object) -> str:
    if isinstance(value, Mapping):
        return json.dumps(dict(value), ensure_ascii=False, default=str)
    return "{}"


def pg_vector_text(values: Sequence[float]) -> str:
    return "[" + ",".join(str(float(value)) for value in values) + "]"


def json_object_from_db(value: object) -> dict[str, object]:
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}

    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return {}
        if isinstance(decoded, Mapping):
            return {str(key): item for key, item in decoded.items()}

    return {}


def json_list_from_db(value: object) -> list[object]:
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)

    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return []
        if isinstance(decoded, list):
            return decoded

    return []


def optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float | str):
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
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
    items = json_list_from_db(value)
    return tuple(
        normalized
        for item in items
        if isinstance(item, str)
        for normalized in (" ".join(item.split()),)
        if normalized
    )


def _clean_quote(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return " ".join(value.split())


def _mapping_source_ref_payload(payload: Mapping[str, object]) -> dict[str, object]:
    quote = _clean_quote(payload.get("quote"))
    if not quote:
        return {}

    result: dict[str, object] = {
        "source_index": optional_int(payload.get("source_index")) or 0,
        "quote": quote,
    }

    source_chunk_id = payload.get("source_chunk_id")
    if source_chunk_id:
        result["source_chunk_id"] = str(source_chunk_id)

    start_offset = optional_int(payload.get("start_offset"))
    if start_offset is not None:
        result["start_offset"] = start_offset

    end_offset = optional_int(payload.get("end_offset"))
    if end_offset is not None:
        result["end_offset"] = end_offset

    confidence = optional_float(payload.get("confidence"))
    if confidence is not None:
        result["confidence"] = confidence

    return result


def source_ref_payload(ref: SourceRefView | Mapping[str, object]) -> dict[str, object]:
    if isinstance(ref, SourceRefView):
        payload: dict[str, object] = {
            "source_index": ref.source_index,
            "quote": ref.quote,
        }
        if ref.source_chunk_id:
            payload["source_chunk_id"] = ref.source_chunk_id
        if ref.start_offset is not None:
            payload["start_offset"] = ref.start_offset
        if ref.end_offset is not None:
            payload["end_offset"] = ref.end_offset
        if ref.confidence is not None:
            payload["confidence"] = ref.confidence
        return payload

    return _mapping_source_ref_payload(ref)


def source_ref_view_from_mapping(payload: Mapping[str, object]) -> SourceRefView:
    normalized = _mapping_source_ref_payload(payload)
    if not normalized:
        raise ValueError("source ref payload requires non-empty quote")

    return SourceRefView(
        source_index=cast(int, normalized["source_index"]),
        quote=cast(str, normalized["quote"]),
        source_chunk_id=cast(str | None, normalized.get("source_chunk_id")),
        start_offset=cast(int | None, normalized.get("start_offset")),
        end_offset=cast(int | None, normalized.get("end_offset")),
        confidence=cast(float | None, normalized.get("confidence")),
    )


def source_ref_views_from_payload(value: object) -> tuple[SourceRefView, ...]:
    if not isinstance(value, Iterable) or isinstance(value, str | bytes | Mapping):
        return ()

    refs: list[SourceRefView] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        try:
            refs.append(source_ref_view_from_mapping(item))
        except ValueError:
            continue
    return tuple(refs)


def first_source_excerpt(source_refs: tuple[SourceRefView, ...]) -> str | None:
    for ref in source_refs:
        quote = _clean_quote(ref.quote)
        if quote:
            return quote
    return None


__all__ = [
    "first_source_excerpt",
    "json_list_from_db",
    "json_object_from_db",
    "jsonb_object_payload",
    "normalize_timestamp",
    "optional_float",
    "optional_int",
    "pg_vector_text",
    "source_ref_payload",
    "source_ref_view_from_mapping",
    "source_ref_views_from_payload",
    "text_tuple_from_json",
]
