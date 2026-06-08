from __future__ import annotations

from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.source_management.domain.entities.source_document import (
    SourceDocument,
)
from src.contexts.knowledge_workbench.source_management.domain.events.source_events import (
    SourceDocumentCreated,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_format import (
    SourceFormat,
)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def test_source_document_requires_non_empty_hash() -> None:
    with pytest.raises(ValueError):
        SourceDocument(
            document_ref=SourceDocumentRef("document-1"),
            source_format=SourceFormat.MARKDOWN,
            content_hash=" ",
            created_at=_now(),
        )


def test_source_document_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError):
        SourceDocument(
            document_ref=SourceDocumentRef("document-1"),
            source_format=SourceFormat.MARKDOWN,
            content_hash="sha256:abc",
            created_at=datetime(2026, 6, 8, 12, 0),
        )


def test_source_document_rejects_empty_original_filename() -> None:
    with pytest.raises(ValueError):
        SourceDocument(
            document_ref=SourceDocumentRef("document-1"),
            source_format=SourceFormat.MARKDOWN,
            content_hash="sha256:abc",
            created_at=_now(),
            original_filename=" ",
        )


def test_source_format_values_are_exactly_expected() -> None:
    assert tuple(item.value for item in SourceFormat) == (
        "markdown",
        "pdf",
        "excel",
        "html",
        "plain_text",
    )


def test_source_document_created_event_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError):
        SourceDocumentCreated(
            document_ref=SourceDocumentRef("document-1"),
            occurred_at=datetime(2026, 6, 8, 12, 0),
        )
