from dataclasses import dataclass
from enum import StrEnum


class DocumentSegmentKind(StrEnum):
    DOCUMENT_PREAMBLE = "DOCUMENT_PREAMBLE"
    SECTION = "SECTION"
    SUBSECTION = "SUBSECTION"
    SPLIT_FRAGMENT = "SPLIT_FRAGMENT"
    PARAGRAPH_GROUP = "PARAGRAPH_GROUP"


@dataclass(frozen=True, slots=True)
class DocumentSegment:
    segment_key: str
    kind: DocumentSegmentKind
    text: str
    heading_path: tuple[str, ...]
    ordinal: int
    estimated_tokens: int

    def __post_init__(self) -> None:
        if not isinstance(self.segment_key, str) or not self.segment_key.strip():
            raise ValueError("segment_key must be non-empty")
        if not isinstance(self.kind, DocumentSegmentKind):
            raise TypeError("kind must be DocumentSegmentKind")
        if not isinstance(self.text, str) or not self.text.strip():
            raise ValueError("text must be non-empty")
        if not isinstance(self.heading_path, tuple):
            raise TypeError("heading_path must be tuple[str, ...]")
        for heading in self.heading_path:
            if not isinstance(heading, str):
                raise TypeError("heading_path must be tuple[str, ...]")
            if not heading.strip():
                raise ValueError("heading_path must not contain empty headings")
        if not isinstance(self.ordinal, int):
            raise TypeError("ordinal must be int")
        if self.ordinal < 0:
            raise ValueError("ordinal must be >= 0")
        if not isinstance(self.estimated_tokens, int):
            raise TypeError("estimated_tokens must be int")
        if self.estimated_tokens <= 0:
            raise ValueError("estimated_tokens must be > 0")
