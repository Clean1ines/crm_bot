from __future__ import annotations

import re

from src.domain.project_plane.knowledge_chunks import (
    KnowledgeChunkDraft,
    KnowledgeSectionPath,
)
from src.domain.project_plane.knowledge_document_structure import KnowledgeDocumentBlock
from src.domain.project_plane.knowledge_semantic_markers import (
    MARKDOWN_HEADER_PATTERN,
    MARKDOWN_HEADER_STRIP_PATTERN,
    SEMANTIC_BUILDER_VERSION,
    SEMANTIC_TAG_STOP_WORDS,
    SEMANTIC_TAG_TERM_PATTERN,
)


def build_knowledge_chunk_drafts(
    *,
    document_title: str,
    blocks: tuple[KnowledgeDocumentBlock, ...],
) -> tuple[KnowledgeChunkDraft, ...]:
    """Convert parser-level document blocks into typed semantic chunk drafts."""

    drafts: list[KnowledgeChunkDraft] = []

    for block in blocks:
        title = block.title or _first_markdown_title(block.content)
        headings = block.headings
        if not headings and title:
            headings = (title,)

        metadata: dict[str, object] = dict(block.metadata)
        metadata.setdefault("semantic_builder", SEMANTIC_BUILDER_VERSION)

        drafts.append(
            KnowledgeChunkDraft(
                content=block.content,
                title=title,
                source_excerpt=_source_excerpt_from_block(block.content),
                section_path=KnowledgeSectionPath(
                    document_title=document_title,
                    headings=headings,
                ),
                tags=tuple(_tags_from_title(title)),
                metadata=metadata,
            )
        )

    return tuple(drafts)


def _first_markdown_title(content: str) -> str:
    for line in content.splitlines():
        stripped = line.strip()
        if _is_markdown_header(stripped):
            return _header_text(stripped)
    return ""


def _source_excerpt_from_block(content: str, *, max_chars: int = 420) -> str:
    logical_text = _markdown_logical_text(content)
    body_lines: list[str] = []

    for line in logical_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if _is_markdown_header(stripped):
            continue
        if re.fullmatch(r"[-*_]{3,}", stripped):
            continue
        body_lines.append(stripped)

    excerpt = " ".join(body_lines)
    if not excerpt:
        excerpt = _first_markdown_title(content) or " ".join(logical_text.split())

    excerpt = " ".join(excerpt.split())
    if len(excerpt) <= max_chars:
        return excerpt
    return excerpt[:max_chars].rstrip() + "..."


def _markdown_logical_text(content: str) -> str:
    lines = [line.rstrip() for line in content.replace("\r", "\n").split("\n")]
    return "\n".join(line for line in lines if line.strip())


def _tags_from_title(title: str, *, max_tags: int = 8) -> list[str]:
    if not title:
        return []

    tags: list[str] = []
    for token in re.findall(SEMANTIC_TAG_TERM_PATTERN, title.lower()):
        token = token.strip("_-.")
        if len(token) < 4 or token in SEMANTIC_TAG_STOP_WORDS or token.isdigit():
            continue
        if token not in tags:
            tags.append(token)
        if len(tags) >= max_tags:
            break

    return tags


def _is_markdown_header(line: str) -> bool:
    return bool(re.match(MARKDOWN_HEADER_PATTERN, line.strip()))


def _header_text(line: str) -> str:
    return re.sub(MARKDOWN_HEADER_STRIP_PATTERN, "", line.strip()).strip()
