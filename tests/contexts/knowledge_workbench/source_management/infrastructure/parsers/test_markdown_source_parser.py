from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.source_management.domain.entities.source_document import (
    SourceDocument,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_format import (
    SourceFormat,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_kind import (
    SourceUnitKind,
)
from src.contexts.knowledge_workbench.source_management.infrastructure.parsers.markdown_source_parser import (
    MarkdownSourceParser,
)


ROOT = Path(__file__).resolve().parents[6]
MARKDOWN_SOURCE_PARSER = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "source_management"
    / "infrastructure"
    / "parsers"
    / "markdown_source_parser.py"
)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _document() -> SourceDocument:
    return SourceDocument(
        document_ref=SourceDocumentRef("document-1"),
        source_format=SourceFormat.MARKDOWN,
        content_hash="sha256:abc",
        created_at=_now(),
        original_filename="knowledge.md",
    )


def test_no_headings_produces_one_document_unit() -> None:
    units = MarkdownSourceParser().parse(
        document=_document(),
        raw_text="Plain paragraph.\n\nAnother paragraph.",
    )

    assert len(units) == 1
    assert units[0].unit_ref.value == "document-1.unit.0"
    assert units[0].unit_kind is SourceUnitKind.DOCUMENT
    assert units[0].text.value == "Plain paragraph.\n\nAnother paragraph."
    assert units[0].heading_path.parts == ()


def test_headings_split_by_highest_level_headings_only() -> None:
    units = MarkdownSourceParser().parse(
        document=_document(),
        raw_text=(
            "# First\n"
            "Intro.\n\n"
            "## Nested details\n"
            "Nested content must stay inside first unit.\n\n"
            "# Second\n"
            "Second content.\n"
            "### Deep nested detail\n"
            "Deep content must stay inside second unit."
        ),
    )

    assert len(units) == 2
    assert tuple(unit.unit_kind for unit in units) == (
        SourceUnitKind.SECTION,
        SourceUnitKind.SECTION,
    )
    assert tuple(unit.heading_path.parts for unit in units) == (
        ("First",),
        ("Second",),
    )
    assert "## Nested details" in units[0].text.value
    assert "### Deep nested detail" in units[1].text.value


def test_when_top_level_is_h2_parser_splits_into_subsections() -> None:
    units = MarkdownSourceParser().parse(
        document=_document(),
        raw_text=(
            "## First subsection\n"
            "First content.\n\n"
            "### Nested detail\n"
            "Nested content.\n\n"
            "## Second subsection\n"
            "Second content."
        ),
    )

    assert len(units) == 2
    assert tuple(unit.unit_kind for unit in units) == (
        SourceUnitKind.SUBSECTION,
        SourceUnitKind.SUBSECTION,
    )
    assert tuple(unit.heading_path.parts for unit in units) == (
        ("First subsection",),
        ("Second subsection",),
    )


def test_order_and_refs_are_preserved() -> None:
    units = MarkdownSourceParser().parse(
        document=_document(),
        raw_text="# A\nA content.\n\n# B\nB content.\n\n# C\nC content.",
    )

    assert tuple(unit.unit_ref.value for unit in units) == (
        "document-1.unit.0",
        "document-1.unit.1",
        "document-1.unit.2",
    )
    assert tuple(unit.ordinal for unit in units) == (0, 1, 2)
    assert tuple(unit.text.value.splitlines()[0] for unit in units) == (
        "# A",
        "# B",
        "# C",
    )


def test_empty_raw_text_rejected() -> None:
    with pytest.raises(ValueError):
        MarkdownSourceParser().parse(document=_document(), raw_text="   ")


def test_parser_does_not_import_runtime_provider_or_artifact_boundaries() -> None:
    text = MARKDOWN_SOURCE_PARSER.read_text(encoding="utf-8")

    forbidden_markers = (
        "llm_runtime",
        "execution_runtime",
        "artifact_runtime",
        "Groq",
        "groq",
        "Qwen",
        "qwen",
        "PromptFit",
        "prompt_fit",
        "WorkItem",
        "LlmTask",
        "PipelineArtifact",
        "Postgres",
        "postgres",
    )

    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not offenders
