from __future__ import annotations

from enum import StrEnum


class SourceFormat(StrEnum):
    MARKDOWN = "markdown"
    PDF = "pdf"
    EXCEL = "excel"
    HTML = "html"
    PLAIN_TEXT = "plain_text"
