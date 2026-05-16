from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class SemanticSourceUnitRole(StrEnum):
    FAQ_CONTAINER = "faq_container"
    SINGLE_ANSWER = "single_answer"
    TEST_SUITE = "test_suite"
    INSTRUCTION_REFERENCE = "instruction_reference"
    MIXED = "mixed"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class SourceSpan:
    start_offset: int
    end_offset: int
    section_path: tuple[str, ...] = ()
    excerpt: str = ""

    def __post_init__(self) -> None:
        if self.start_offset < 0:
            raise ValueError("SourceSpan.start_offset must be non-negative")
        if self.end_offset < self.start_offset:
            raise ValueError("SourceSpan.end_offset must be >= start_offset")

        object.__setattr__(
            self,
            "section_path",
            tuple(
                " ".join(part.strip().split())
                for part in self.section_path
                if part.strip()
            ),
        )
        object.__setattr__(self, "excerpt", self.excerpt.strip())


@dataclass(frozen=True, slots=True)
class MarkdownKnowledgeSubsection:
    title: str
    body: str
    level: int
    span: SourceSpan

    def __post_init__(self) -> None:
        title = " ".join(self.title.strip().split())
        body = self.body.strip()
        if not title:
            raise ValueError("MarkdownKnowledgeSubsection.title must not be blank")
        if self.level < 1:
            raise ValueError("MarkdownKnowledgeSubsection.level must be positive")
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "body", body)

    @property
    def source_excerpt(self) -> str:
        return self.span.excerpt or self.to_markdown()

    def to_markdown(self) -> str:
        marker = "#" * self.level
        if self.body:
            return f"{marker} {self.title}\n\n{self.body}".strip()
        return f"{marker} {self.title}"


@dataclass(frozen=True, slots=True)
class MarkdownKnowledgeSection:
    title: str
    body: str
    level: int
    span: SourceSpan
    children: tuple[MarkdownKnowledgeSubsection, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        title = " ".join(self.title.strip().split())
        body = self.body.strip()
        if not title:
            raise ValueError("MarkdownKnowledgeSection.title must not be blank")
        if self.level < 1:
            raise ValueError("MarkdownKnowledgeSection.level must be positive")
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "body", body)
        object.__setattr__(self, "children", tuple(self.children))

    @property
    def section_path(self) -> tuple[str, ...]:
        return self.span.section_path

    @property
    def source_excerpt(self) -> str:
        return self.span.excerpt or self.to_markdown()

    def to_markdown(self) -> str:
        marker = "#" * self.level
        parts = [f"{marker} {self.title}"]
        if self.body:
            parts.append(self.body)
        parts.extend(child.to_markdown() for child in self.children)
        return "\n\n".join(part for part in parts if part.strip()).strip()


@dataclass(frozen=True, slots=True)
class SemanticSourceUnit:
    id: str
    document_title: str
    source_format: str
    title: str
    body: str
    section_path: tuple[str, ...]
    source_span: SourceSpan
    children: tuple[MarkdownKnowledgeSubsection, ...] = field(default_factory=tuple)
    role_hint: SemanticSourceUnitRole = SemanticSourceUnitRole.UNKNOWN
    metadata: dict[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        unit_id = self.id.strip()
        title = " ".join(self.title.strip().split())
        document_title = self.document_title.strip()
        if not unit_id:
            raise ValueError("SemanticSourceUnit.id must not be blank")
        if not title:
            raise ValueError("SemanticSourceUnit.title must not be blank")
        if not document_title:
            raise ValueError("SemanticSourceUnit.document_title must not be blank")

        object.__setattr__(self, "id", unit_id)
        object.__setattr__(self, "title", title)
        object.__setattr__(self, "document_title", document_title)
        object.__setattr__(self, "body", self.body.strip())
        object.__setattr__(
            self,
            "section_path",
            tuple(part.strip() for part in self.section_path if part.strip()),
        )
        object.__setattr__(self, "children", tuple(self.children))
        object.__setattr__(self, "metadata", dict(self.metadata))

    @property
    def source_excerpt(self) -> str:
        return self.source_span.excerpt or self.to_markdown()

    def to_markdown(self) -> str:
        section = MarkdownKnowledgeSection(
            title=self.title,
            body=self.body,
            level=2,
            span=self.source_span,
            children=self.children,
        )
        return section.to_markdown()
