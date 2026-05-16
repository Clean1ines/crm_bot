from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Final

from src.domain.project_plane.knowledge_acquisition import (
    MarkdownKnowledgeSection,
    MarkdownKnowledgeSubsection,
    SemanticSourceUnit,
    SemanticSourceUnitRole,
    SourceSpan,
)

_MARKDOWN_HEADING_RE: Final[re.Pattern[str]] = re.compile(
    r"(?m)^(#{1,6})[ \t]+(.+?)\s*$"
)


@dataclass(frozen=True, slots=True)
class ParsedMarkdownKnowledgeDocument:
    document_title: str
    source_text: str
    sections: tuple[MarkdownKnowledgeSection, ...]


@dataclass(frozen=True, slots=True)
class _Heading:
    level: int
    title: str
    start: int
    end: int


class MarkdownStructureExtractor:
    """Structure-only Markdown extractor.

    It preserves heading hierarchy and source spans. It does not decide final
    production cards and does not use business-term dictionaries.
    """

    def extract(
        self,
        *,
        document_title: str,
        source_text: str,
    ) -> ParsedMarkdownKnowledgeDocument:
        normalized = _normalize_markdown_source(source_text)
        title = document_title.strip() or "markdown document"
        sections = _extract_level_2_sections(title, normalized)
        if sections:
            return ParsedMarkdownKnowledgeDocument(
                document_title=title,
                source_text=normalized,
                sections=sections,
            )

        fallback_text = normalized.strip()
        if not fallback_text:
            return ParsedMarkdownKnowledgeDocument(
                document_title=title,
                source_text=normalized,
                sections=(),
            )

        span = SourceSpan(
            start_offset=0,
            end_offset=len(normalized),
            section_path=(title,),
            excerpt=fallback_text,
        )
        return ParsedMarkdownKnowledgeDocument(
            document_title=title,
            source_text=normalized,
            sections=(
                MarkdownKnowledgeSection(
                    title=title,
                    body=fallback_text,
                    level=2,
                    span=span,
                    children=(),
                ),
            ),
        )

    def to_semantic_units(
        self,
        document: ParsedMarkdownKnowledgeDocument,
    ) -> tuple[SemanticSourceUnit, ...]:
        units: list[SemanticSourceUnit] = []
        for index, section in enumerate(document.sections):
            digest = hashlib.sha256(
                (
                    f"{document.document_title}:"
                    f"{index}:"
                    f"{section.title}:"
                    f"{section.span.start_offset}"
                ).encode("utf-8")
            ).hexdigest()[:16]
            units.append(
                SemanticSourceUnit(
                    id=f"markdown-section-{index}-{digest}",
                    document_title=document.document_title,
                    source_format="markdown",
                    title=section.title,
                    body=section.body,
                    children=section.children,
                    section_path=section.section_path,
                    source_span=section.span,
                    role_hint=SemanticSourceUnitRole.UNKNOWN,
                    metadata={
                        "markdown_heading_level": section.level,
                        "markdown_child_section_count": len(section.children),
                    },
                )
            )
        return tuple(units)


def _normalize_markdown_source(source_text: str) -> str:
    text = source_text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()


def _headings(source_text: str) -> tuple[_Heading, ...]:
    result: list[_Heading] = []
    for match in _MARKDOWN_HEADING_RE.finditer(source_text):
        result.append(
            _Heading(
                level=len(match.group(1)),
                title=match.group(2).strip(),
                start=match.start(),
                end=match.end(),
            )
        )
    return tuple(result)


def _extract_level_2_sections(
    document_title: str,
    source_text: str,
) -> tuple[MarkdownKnowledgeSection, ...]:
    headings = _headings(source_text)
    primary_indexes = [
        index for index, heading in enumerate(headings) if heading.level == 2
    ]
    sections: list[MarkdownKnowledgeSection] = []

    for ordinal, heading_index in enumerate(primary_indexes):
        heading = headings[heading_index]
        next_primary_heading_index = (
            primary_indexes[ordinal + 1] if ordinal + 1 < len(primary_indexes) else None
        )
        section_end = (
            headings[next_primary_heading_index].start
            if next_primary_heading_index is not None
            else len(source_text)
        )

        child_heading_candidates = (
            headings[heading_index + 1 : next_primary_heading_index]
            if next_primary_heading_index is not None
            else headings[heading_index + 1 :]
        )
        child_headings = tuple(
            candidate for candidate in child_heading_candidates if candidate.level == 3
        )

        body_end = child_headings[0].start if child_headings else section_end
        body = source_text[heading.end : body_end].strip()
        section_path = (document_title, heading.title)
        children = _extract_level_3_children(
            source_text=source_text,
            section_end=section_end,
            document_title=document_title,
            parent_title=heading.title,
            child_headings=child_headings,
        )
        excerpt = source_text[heading.start : section_end].strip()
        span = SourceSpan(
            start_offset=heading.start,
            end_offset=section_end,
            section_path=section_path,
            excerpt=excerpt,
        )
        sections.append(
            MarkdownKnowledgeSection(
                title=heading.title,
                body=body,
                level=heading.level,
                span=span,
                children=children,
            )
        )

    return tuple(sections)


def _extract_level_3_children(
    *,
    source_text: str,
    section_end: int,
    document_title: str,
    parent_title: str,
    child_headings: tuple[_Heading, ...],
) -> tuple[MarkdownKnowledgeSubsection, ...]:
    children: list[MarkdownKnowledgeSubsection] = []

    for index, child in enumerate(child_headings):
        child_end = (
            child_headings[index + 1].start
            if index + 1 < len(child_headings)
            else section_end
        )
        body = source_text[child.end : child_end].strip()
        excerpt = source_text[child.start : child_end].strip()
        children.append(
            MarkdownKnowledgeSubsection(
                title=child.title,
                body=body,
                level=child.level,
                span=SourceSpan(
                    start_offset=child.start,
                    end_offset=child_end,
                    section_path=(document_title, parent_title, child.title),
                    excerpt=excerpt,
                ),
            )
        )

    return tuple(children)
