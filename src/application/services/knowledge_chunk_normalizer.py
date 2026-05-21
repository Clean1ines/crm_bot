from __future__ import annotations

from collections.abc import Mapping, Sequence

from src.application.ports.logger_port import LoggerPort
from src.domain.project_plane.json_types import JsonObject, json_value_from_unknown


CHUNK_AUDIT_FIELDS: tuple[str, ...] = (
    "content",
    "entry_kind",
    "title",
    "source_excerpt",
    "questions",
    "synonyms",
    "tags",
    "embedding_text",
)


def normalize_knowledge_chunks(raw_chunks: Sequence[object]) -> list[JsonObject]:
    chunks: list[JsonObject] = []
    for chunk in raw_chunks:
        normalized = _normalize_chunk(chunk)
        if normalized is not None:
            chunks.append(normalized)

    return chunks


def log_knowledge_chunk_audit(
    logger: LoggerPort,
    chunks: Sequence[JsonObject],
    *,
    context: str,
) -> None:
    logger.info(
        "Knowledge upload chunk audit",
        extra={
            "context": context,
            "chunk_count": len(chunks),
            "field_counts": _chunk_field_counts(chunks),
            "unknown_field_counts": _chunk_unknown_field_counts(chunks),
            "content_length": _chunk_content_length_stats(chunks),
        },
    )


def _normalize_chunk(chunk: object) -> JsonObject | None:
    if isinstance(chunk, str):
        return _chunk_from_text(chunk)

    if isinstance(chunk, Mapping):
        return _chunk_from_mapping(chunk)

    return None


def _chunk_from_text(value: str) -> JsonObject | None:
    content = value.strip()
    return {"content": content} if content else None


def _chunk_from_mapping(value: Mapping[object, object]) -> JsonObject | None:
    content = str(value.get("content") or "").strip()
    if not content:
        return None

    normalized = {
        str(key): json_value_from_unknown(item) for key, item in value.items()
    }
    normalized["content"] = content
    return normalized


def _is_present_chunk_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, tuple, set, dict)):
        return bool(value)
    return True


def _chunk_field_counts(chunks: Sequence[JsonObject]) -> dict[str, int]:
    return {
        field: sum(1 for chunk in chunks if _is_present_chunk_value(chunk.get(field)))
        for field in CHUNK_AUDIT_FIELDS
    }


def _chunk_unknown_field_counts(chunks: Sequence[JsonObject]) -> dict[str, int]:
    known = set(CHUNK_AUDIT_FIELDS)
    counts: dict[str, int] = {}
    for chunk in chunks:
        for key, value in chunk.items():
            if key in known or not _is_present_chunk_value(value):
                continue
            counts[key] = counts.get(key, 0) + 1
    return counts


def _chunk_content_length_stats(chunks: Sequence[JsonObject]) -> JsonObject:
    lengths = [len(str(chunk.get("content") or "").strip()) for chunk in chunks]
    if not lengths:
        return {"min": 0, "max": 0, "avg": 0}
    return {
        "min": min(lengths),
        "max": max(lengths),
        "avg": round(sum(lengths) / len(lengths), 2),
    }
