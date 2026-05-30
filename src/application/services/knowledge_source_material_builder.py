from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence

from src.application.services.markdown_structure_extractor import (
    MarkdownStructureExtractor,
)
from src.domain.project_plane.json_types import (
    JsonObject,
    json_value_from_unknown,
)
from src.domain.project_plane.knowledge_acquisition import (
    MarkdownKnowledgeSubsection,
    SemanticSourceUnit,
)
from src.domain.project_plane.knowledge_compilation import SourceChunk
from src.domain.project_plane.knowledge_preprocessing import KnowledgePreprocessingMode


_MIN_INDEXABLE_CHUNK_CHARS = 1


def chunk_content(chunk: JsonObject) -> str:
    return str(chunk.get("content") or "").strip()


def _is_separator_chunk(content: str) -> bool:
    normalized = " ".join(content.split())
    return normalized in {"---", "***", "___", "--", "-"} or bool(
        re.fullmatch(r"[-*_]{3,}", normalized)
    )


def _looks_like_broken_fragment(content: str) -> bool:
    normalized = " ".join(content.split())
    if not normalized:
        return True
    if _is_separator_chunk(normalized):
        return True
    if len(normalized) < _MIN_INDEXABLE_CHUNK_CHARS:
        return True
    if normalized[0] in {",", ";", ":", ".", ")", "]"}:
        return True

    # Keep this intentionally conservative. The raw/structured mixing fix is
    # the main production fix; this guard should only remove obvious garbage,
    # not compact but valid FAQ/test chunks.
    return False


def filter_indexable_chunks(chunks: list[JsonObject]) -> list[JsonObject]:
    return [
        chunk
        for chunk in chunks
        if not _looks_like_broken_fragment(chunk_content(chunk))
    ]


def source_chunk_optional_int(value: object) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if value >= 0 else None
    if isinstance(value, float) and value.is_integer():
        converted = int(value)
        return converted if converted >= 0 else None
    if isinstance(value, str) and value.strip().isdigit():
        converted = int(value.strip())
        return converted if converted >= 0 else None
    return None


def _source_chunk_text(value: object) -> str:
    if value is None:
        return ""
    return " ".join(str(value).strip().split())


def _source_chunk_index(chunk: JsonObject, fallback_index: int) -> int:
    raw_index = source_chunk_optional_int(chunk.get("index"))
    return raw_index if raw_index is not None else fallback_index


def build_source_chunks_from_json_chunks(
    *,
    project_id: str,
    document_id: str,
    chunks: list[JsonObject],
) -> tuple[SourceChunk, ...]:
    source_chunks: list[SourceChunk] = []
    used_indices: set[int] = set()

    for fallback_index, chunk in enumerate(chunks):
        content = chunk_content(chunk)
        if not content:
            continue

        source_index = _source_chunk_index(chunk, fallback_index)
        while source_index in used_indices:
            source_index += 1
        used_indices.add(source_index)

        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        metadata: dict[str, object] = {"upload_chunk_index": fallback_index}

        source_chunks.append(
            SourceChunk(
                id=f"{document_id}:{source_index}",
                document_id=document_id,
                project_id=project_id,
                source_index=source_index,
                content=content,
                page=source_chunk_optional_int(chunk.get("page")),
                section_title=_source_chunk_text(
                    chunk.get("section_title") or chunk.get("title")
                ),
                start_offset=source_chunk_optional_int(chunk.get("start_offset")),
                end_offset=source_chunk_optional_int(chunk.get("end_offset")),
                checksum=checksum,
                metadata=metadata,
            )
        )

    return tuple(source_chunks)


def build_json_chunks_from_source_chunks(
    source_chunks: Sequence[SourceChunk],
) -> list[JsonObject]:
    chunks: list[JsonObject] = []
    for source_chunk in source_chunks:
        chunk: JsonObject = {
            "id": source_chunk.id,
            "index": source_chunk.source_index,
            "content": source_chunk.content,
        }
        if source_chunk.page is not None:
            chunk["page"] = source_chunk.page
        if source_chunk.section_title:
            chunk["section_title"] = source_chunk.section_title
        if source_chunk.start_offset is not None:
            chunk["start_offset"] = source_chunk.start_offset
        if source_chunk.end_offset is not None:
            chunk["end_offset"] = source_chunk.end_offset
        chunks.append(chunk)
    return chunks


def is_markdown_file(file_name: str) -> bool:
    return file_name.lower().strip().endswith(".md")


def _source_text_from_json_chunks(chunks: Sequence[JsonObject]) -> str:
    parts: list[str] = []
    for chunk in chunks:
        content = chunk_content(chunk)
        if content:
            parts.append(content)
    return "\n\n".join(parts).strip()


def _markdown_child_payload(child: MarkdownKnowledgeSubsection) -> JsonObject:
    return {
        "title": child.title,
        "body": child.body,
        "source_excerpt": child.source_excerpt,
        "section_path": list(child.span.section_path),
        "start_offset": child.span.start_offset,
        "end_offset": child.span.end_offset,
    }


def _json_object_from_metadata(metadata: Mapping[str, object]) -> JsonObject:
    result: JsonObject = {}
    for key, value in metadata.items():
        result[str(key)] = json_value_from_unknown(value)
    return result


def count_json_array_field_items(
    chunks: Sequence[JsonObject],
    field_name: str,
) -> int:
    total = 0
    for chunk in chunks:
        value = chunk.get(field_name)
        if isinstance(value, list):
            total += len(value)
    return total


def _json_chunk_from_semantic_unit(
    *,
    unit: SemanticSourceUnit,
    index: int,
) -> JsonObject:
    source_excerpt = unit.source_excerpt
    content = unit.to_markdown()
    return {
        "id": unit.id,
        "index": index,
        "content": content,
        "source_format": unit.source_format,
        "semantic_unit_id": unit.id,
        "semantic_unit_role_hint": unit.role_hint.value,
        "section_title": unit.title,
        "section_body": unit.body,
        "section_path": list(unit.section_path),
        "source_excerpt": source_excerpt,
        "start_offset": unit.source_span.start_offset,
        "end_offset": unit.source_span.end_offset,
        "children": [_markdown_child_payload(child) for child in unit.children],
        "source_refs": [
            {
                "source_index": index,
                "section_path": list(unit.source_span.section_path),
                "start_offset": unit.source_span.start_offset,
                "end_offset": unit.source_span.end_offset,
                "excerpt": source_excerpt,
            }
        ],
        "metadata": {
            **_json_object_from_metadata(unit.metadata),
            "kad_v1_semantic_source_unit": True,
            "markdown_section_child_count": len(unit.children),
        },
    }


def _markdown_semantic_source_chunks(
    *,
    file_name: str,
    chunks: Sequence[JsonObject],
) -> list[JsonObject]:
    source_text = _source_text_from_json_chunks(chunks)
    if not source_text:
        return list(chunks)
    if not re.search(r"(?m)^##\s+\S", source_text):
        return list(chunks)

    extractor = MarkdownStructureExtractor()
    document = extractor.extract(document_title=file_name, source_text=source_text)
    units = extractor.to_semantic_units(document)
    if not units:
        return list(chunks)

    return [
        _json_chunk_from_semantic_unit(unit=unit, index=index)
        for index, unit in enumerate(units)
    ]


def build_compiler_source_chunks_for_preprocessing(
    *,
    file_name: str,
    chunks: list[JsonObject],
    mode: KnowledgePreprocessingMode,
) -> list[JsonObject]:
    del mode
    if not is_markdown_file(file_name):
        return chunks
    return _markdown_semantic_source_chunks(file_name=file_name, chunks=chunks)
