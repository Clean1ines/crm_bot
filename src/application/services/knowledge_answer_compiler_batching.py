from __future__ import annotations

import re

from src.application.services.knowledge_source_material_builder import _chunk_content
from src.domain.project_plane.json_types import JsonObject, json_value_from_unknown


KCD_STAGE_K_TECHNICAL_CHUNKS_PER_LLM_CALL = 1
KCD_STAGE_K_TECHNICAL_SOURCE_CHAR_BUDGET = 650


def _split_technical_source_text(
    content: str,
    *,
    char_budget: int,
) -> tuple[str, ...]:
    text = content.strip()
    if not text:
        return ()
    if len(text) <= char_budget:
        return (text,)

    paragraphs = [part.strip() for part in re.split(r"\n\s*\n", text) if part.strip()]
    if not paragraphs:
        return (text,)

    parts: list[str] = []
    current: list[str] = []
    current_len = 0

    for paragraph in paragraphs:
        paragraph_len = len(paragraph)
        additional = paragraph_len if not current else paragraph_len + 2
        if current and current_len + additional > char_budget:
            parts.append("\n\n".join(current))
            current = [paragraph]
            current_len = paragraph_len
            continue
        current.append(paragraph)
        current_len += additional

    if current:
        parts.append("\n\n".join(current))

    return tuple(part for part in parts if part)


def _technical_chunk_part(
    chunk: JsonObject,
    *,
    content: str,
    part_index: int,
    part_count: int,
) -> JsonObject:
    technical_chunk: JsonObject = {
        str(key): json_value_from_unknown(value) for key, value in chunk.items()
    }
    technical_chunk["content"] = content
    technical_chunk["technical_part_index"] = part_index
    technical_chunk["technical_part_count"] = part_count
    technical_chunk["technical_source_char_budget"] = (
        KCD_STAGE_K_TECHNICAL_SOURCE_CHAR_BUDGET
    )
    return technical_chunk


def _technical_chunk_batches_for_answer_compiler(
    chunks: list[JsonObject],
) -> tuple[list[JsonObject], ...]:
    batches: list[list[JsonObject]] = []

    for chunk in chunks:
        content = _chunk_content(chunk)
        if not content:
            continue

        is_markdown_semantic = bool(chunk.get("section_title") or chunk.get("children"))
        parts: tuple[str, ...]
        if is_markdown_semantic:
            parts = (content.strip(),)
        else:
            parts = _split_technical_source_text(
                content,
                char_budget=KCD_STAGE_K_TECHNICAL_SOURCE_CHAR_BUDGET,
            )
        part_count = len(parts)

        for part_index, part_content in enumerate(parts, start=1):
            batches.append(
                [
                    _technical_chunk_part(
                        chunk,
                        content=part_content,
                        part_index=part_index,
                        part_count=part_count,
                    )
                ]
            )

    return tuple(batches)
