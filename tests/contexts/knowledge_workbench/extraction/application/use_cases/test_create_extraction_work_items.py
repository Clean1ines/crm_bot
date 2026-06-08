from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.knowledge_workbench.extraction.application.use_cases.create_extraction_work_items import (
    CLAIM_EXTRACTION_WORK_KIND,
    CreateExtractionWorkItems,
    CreateExtractionWorkItemsCommand,
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


ROOT = Path(__file__).resolve().parents[6]
CREATE_EXTRACTION_WORK_ITEMS = (
    ROOT
    / "src"
    / "contexts"
    / "knowledge_workbench"
    / "extraction"
    / "application"
    / "use_cases"
    / "create_extraction_work_items.py"
)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _source_unit(ref: str, *, ordinal: int = 0) -> SourceUnit:
    return SourceUnit(
        unit_ref=SourceUnitRef(ref),
        document_ref=SourceDocumentRef("document-1"),
        unit_kind=SourceUnitKind.SECTION,
        text=SourceUnitText("Source unit text."),
        heading_path=HeadingPath(("Product",)),
        lineage=SourceUnitLineage(),
        ordinal=ordinal,
        created_at=_now(),
    )


def _execute(
    source_units: tuple[SourceUnit, ...],
    *,
    prompt_id: str = "faq_claim_observations",
):
    return CreateExtractionWorkItems().execute(
        CreateExtractionWorkItemsCommand(
            source_units=source_units,
            prompt_id=prompt_id,
        )
    )


def test_one_source_unit_creates_one_ready_work_item() -> None:
    source_unit = _source_unit("document-1.unit.0")

    result = _execute((source_unit,))

    assert len(result.work_items) == 1
    work_item = result.work_items[0]
    assert work_item.work_item_id == (
        "claim-extraction:faq_claim_observations:document-1.unit.0"
    )
    assert work_item.work_kind == CLAIM_EXTRACTION_WORK_KIND
    assert work_item.work_kind.value == "knowledge_workbench.claim_extraction"
    assert work_item.status is WorkItemStatus.READY
    assert work_item.attempt_count == 0


def test_multiple_source_units_preserve_order() -> None:
    source_units = (
        _source_unit("document-1.unit.0", ordinal=0),
        _source_unit("document-1.unit.1", ordinal=1),
        _source_unit("document-1.unit.2", ordinal=2),
    )

    result = _execute(source_units)

    assert tuple(work_item.work_item_id for work_item in result.work_items) == (
        "claim-extraction:faq_claim_observations:document-1.unit.0",
        "claim-extraction:faq_claim_observations:document-1.unit.1",
        "claim-extraction:faq_claim_observations:document-1.unit.2",
    )


def test_work_item_ids_are_deterministic_for_prompt_and_source_unit_ref() -> None:
    source_unit = _source_unit("document-1.unit.7")

    first = _execute((source_unit,), prompt_id="prompt_a").work_items[0]
    second = _execute((source_unit,), prompt_id="prompt_a").work_items[0]

    assert first.work_item_id == second.work_item_id
    assert first.work_item_id == "claim-extraction:prompt_a:document-1.unit.7"


def test_empty_source_units_rejected() -> None:
    with pytest.raises(ValueError):
        CreateExtractionWorkItemsCommand(
            source_units=(),
            prompt_id="faq_claim_observations",
        )


def test_empty_prompt_id_rejected() -> None:
    with pytest.raises(ValueError):
        CreateExtractionWorkItemsCommand(
            source_units=(_source_unit("document-1.unit.0"),),
            prompt_id=" ",
        )


def test_work_kind_is_exactly_claim_extraction() -> None:
    result = _execute((_source_unit("document-1.unit.0"),))

    assert tuple(work_item.work_kind.value for work_item in result.work_items) == (
        "knowledge_workbench.claim_extraction",
    )


def test_use_case_does_not_persist_parse_or_touch_provider_artifact_or_llm_task() -> (
    None
):
    text = CREATE_EXTRACTION_WORK_ITEMS.read_text(encoding="utf-8")

    forbidden_markers = (
        "UnitOfWork",
        "unit_of_work",
        "Repository",
        "repository",
        ".commit(",
        ".rollback(",
        "SourceParser",
        "Markdown",
        "markdown",
        "llm_runtime",
        "LlmTask",
        "PipelineArtifact",
        "artifact_runtime",
        "Groq",
        "groq",
        "Qwen",
        "qwen",
        "provider",
    )

    offenders = [marker for marker in forbidden_markers if marker in text]

    assert not offenders
