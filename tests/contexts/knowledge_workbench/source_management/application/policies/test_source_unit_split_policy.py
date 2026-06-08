from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.source_management.application.policies.source_unit_split_policy import (
    SourceUnitCannotBeSplitFurther,
    SourceUnitSplitCommand,
    SourceUnitSplitPolicy,
    SourceUnitSplitWouldNotReduceInput,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
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


ROOT = Path(__file__).resolve().parents[6]
SOURCE_UNIT_SPLIT_POLICY = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "source_management"
    / "application"
    / "policies"
    / "source_unit_split_policy.py"
)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _source_unit(
    *,
    text: str,
    ordinal: int = 3,
    heading_path: HeadingPath | None = None,
) -> SourceUnit:
    return SourceUnit(
        unit_ref=SourceUnitRef("document-1.unit.3"),
        document_ref=SourceDocumentRef("document-1"),
        unit_kind=SourceUnitKind.SECTION,
        text=SourceUnitText(text),
        heading_path=heading_path or HeadingPath(("Product", "Limits")),
        lineage=SourceUnitLineage(),
        ordinal=ordinal,
        created_at=_now(),
    )


def _split(
    source_unit: SourceUnit, *, max_child_characters: int
) -> tuple[SourceUnit, ...]:
    result = SourceUnitSplitPolicy().split(
        SourceUnitSplitCommand(
            source_unit=source_unit,
            reason=SplitReason.PROMPT_FIT,
            max_child_characters=max_child_characters,
        )
    )

    assert result.parent_unit == source_unit
    return result.child_units


def test_split_multi_paragraph_source_into_children() -> None:
    source_unit = _source_unit(
        text="First paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    )

    child_units = _split(source_unit, max_child_characters=25)

    assert tuple(child.text.value for child in child_units) == (
        "First paragraph.",
        "Second paragraph.",
        "Third paragraph.",
    )
    assert tuple(child.unit_kind for child in child_units) == (
        SourceUnitKind.SPLIT_FRAGMENT,
        SourceUnitKind.SPLIT_FRAGMENT,
        SourceUnitKind.SPLIT_FRAGMENT,
    )


def test_child_refs_are_deterministic() -> None:
    source_unit = _source_unit(text="Alpha.\n\nBeta.\n\nGamma.")

    child_units = _split(source_unit, max_child_characters=10)

    assert tuple(child.unit_ref.value for child in child_units) == (
        "document-1.unit.3.split.0",
        "document-1.unit.3.split.1",
        "document-1.unit.3.split.2",
    )


def test_children_preserve_document_ref() -> None:
    source_unit = _source_unit(text="Alpha.\n\nBeta.")

    child_units = _split(source_unit, max_child_characters=10)

    assert tuple(child.document_ref for child in child_units) == (
        source_unit.document_ref,
        source_unit.document_ref,
    )


def test_children_preserve_heading_path() -> None:
    heading_path = HeadingPath(("A", "B", "C"))
    source_unit = _source_unit(text="Alpha.\n\nBeta.", heading_path=heading_path)

    child_units = _split(source_unit, max_child_characters=10)

    assert tuple(child.heading_path for child in child_units) == (
        heading_path,
        heading_path,
    )


def test_children_lineage_points_to_parent() -> None:
    source_unit = _source_unit(text="Alpha.\n\nBeta.")

    child_units = _split(source_unit, max_child_characters=10)

    assert tuple(child.lineage.parent_refs for child in child_units) == (
        (source_unit.unit_ref,),
        (source_unit.unit_ref,),
    )


def test_child_ordinals_preserve_order() -> None:
    source_unit = _source_unit(text="Alpha.\n\nBeta.\n\nGamma.", ordinal=7)

    child_units = _split(source_unit, max_child_characters=10)

    assert tuple(child.ordinal for child in child_units) == (7000, 7001, 7002)


def test_paragraphs_are_grouped_when_they_fit_child_limit() -> None:
    source_unit = _source_unit(text="A.\n\nB.\n\nLong paragraph.")

    child_units = _split(source_unit, max_child_characters=16)

    assert tuple(child.text.value for child in child_units) == (
        "A.\n\nB.",
        "Long paragraph.",
    )


def test_cannot_split_single_oversized_paragraph() -> None:
    source_unit = _source_unit(text="This paragraph is too long.")

    with pytest.raises(SourceUnitCannotBeSplitFurther):
        _split(source_unit, max_child_characters=10)


def test_cannot_split_into_one_child() -> None:
    source_unit = _source_unit(text="Alpha.\n\nBeta.")

    with pytest.raises(SourceUnitSplitWouldNotReduceInput):
        _split(source_unit, max_child_characters=20)


def test_invalid_max_child_characters_rejected() -> None:
    with pytest.raises(ValueError):
        SourceUnitSplitCommand(
            source_unit=_source_unit(text="Alpha.\n\nBeta."),
            reason=SplitReason.PROMPT_FIT,
            max_child_characters=0,
        )


def test_source_unit_split_policy_does_not_import_runtime_db_or_markdown_adapters() -> (
    None
):
    text = SOURCE_UNIT_SPLIT_POLICY.read_text(encoding="utf-8")

    forbidden_markers = (
        "llm_runtime",
        "execution_runtime",
        "artifact_runtime",
        "Groq",
        "groq",
        "Qwen",
        "qwen",
        "PipelineArtifact",
        "WorkItem",
        "LlmTask",
        "Markdown",
        "markdown",
        "Postgres",
        "postgres",
    )

    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not offenders
