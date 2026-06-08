from __future__ import annotations

from enum import StrEnum


class SourceUnitKind(StrEnum):
    DOCUMENT = "document"
    SECTION = "section"
    SUBSECTION = "subsection"
    PARAGRAPH_GROUP = "paragraph_group"
    TABLE = "table"
    SHEET = "sheet"
    ROW_GROUP = "row_group"
    SPLIT_FRAGMENT = "split_fragment"
