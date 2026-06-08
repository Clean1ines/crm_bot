from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from typing import cast

import pytest

from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)
from src.contexts.knowledge_workbench.source_management.domain.events.source_events import (
    SourceUnitCreated,
    SourceUnitSplit,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.heading_path import (
    HeadingPath,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_kind import (
    SourceUnitKind,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_lineage import (
    SourceUnitLineage,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_text import (
    SourceUnitText,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.split_reason import (
    SplitReason,
)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _source_unit() -> SourceUnit:
    return SourceUnit(
        unit_ref=SourceUnitRef("document-1.unit.0"),
        document_ref=SourceDocumentRef("document-1"),
        unit_kind=SourceUnitKind.SECTION,
        text=SourceUnitText("# Product\n\nSystem turns documents into knowledge."),
        heading_path=HeadingPath(("Product",)),
        lineage=SourceUnitLineage(),
        ordinal=0,
        created_at=_now(),
    )


def test_source_unit_accepts_valid_unit() -> None:
    unit = _source_unit()

    assert unit.unit_ref == SourceUnitRef("document-1.unit.0")
    assert unit.document_ref == SourceDocumentRef("document-1")
    assert unit.unit_kind is SourceUnitKind.SECTION
    assert unit.text.value.startswith("# Product")


def test_source_unit_requires_non_empty_text() -> None:
    with pytest.raises(ValueError):
        SourceUnitText(" ")


def test_source_unit_rejects_negative_ordinal() -> None:
    with pytest.raises(ValueError):
        SourceUnit(
            unit_ref=SourceUnitRef("document-1.unit.-1"),
            document_ref=SourceDocumentRef("document-1"),
            unit_kind=SourceUnitKind.SECTION,
            text=SourceUnitText("Text"),
            heading_path=HeadingPath(("Product",)),
            lineage=SourceUnitLineage(),
            ordinal=-1,
            created_at=_now(),
        )


def test_source_unit_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError):
        SourceUnit(
            unit_ref=SourceUnitRef("document-1.unit.0"),
            document_ref=SourceDocumentRef("document-1"),
            unit_kind=SourceUnitKind.SECTION,
            text=SourceUnitText("Text"),
            heading_path=HeadingPath(("Product",)),
            lineage=SourceUnitLineage(),
            ordinal=0,
            created_at=datetime(2026, 6, 8, 12, 0),
        )


def test_source_lineage_rejects_duplicate_parent_refs() -> None:
    parent_ref = SourceUnitRef("document-1.unit.0")

    with pytest.raises(ValueError):
        SourceUnitLineage((parent_ref, parent_ref))


def test_heading_path_is_immutable_and_copy_safe() -> None:
    raw_parts = ["Root", "Child"]
    heading_path = HeadingPath(cast(tuple[str, ...], raw_parts))

    raw_parts.append("Mutated")

    assert heading_path.parts == ("Root", "Child")
    with pytest.raises(FrozenInstanceError):
        heading_path.parts = ("Other",)


def test_source_unit_kind_values_are_exactly_expected() -> None:
    assert tuple(item.value for item in SourceUnitKind) == (
        "document",
        "section",
        "subsection",
        "paragraph_group",
        "table",
        "sheet",
        "row_group",
        "split_fragment",
    )


def test_split_reason_values_are_exactly_expected() -> None:
    assert tuple(item.value for item in SplitReason) == (
        "initial_parse",
        "prompt_fit",
        "request_too_large",
        "output_too_large",
        "user_forced",
    )


def test_source_unit_created_event_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError):
        SourceUnitCreated(
            unit_ref=SourceUnitRef("document-1.unit.0"),
            document_ref=SourceDocumentRef("document-1"),
            occurred_at=datetime(2026, 6, 8, 12, 0),
        )


def test_source_unit_split_event_requires_timezone_aware_timestamp() -> None:
    with pytest.raises(ValueError):
        SourceUnitSplit(
            parent_unit_ref=SourceUnitRef("document-1.unit.0"),
            child_unit_refs=(SourceUnitRef("document-1.unit.0.split.0"),),
            reason=SplitReason.PROMPT_FIT,
            occurred_at=datetime(2026, 6, 8, 12, 0),
        )
