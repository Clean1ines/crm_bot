from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.knowledge_workbench.application.sagas.plan_draft_observation_extraction_work import (
    DraftObservationExtractionWorkPlan,
    PlanDraftObservationExtractionWork,
    PlanDraftObservationExtractionWorkCommand,
    PlanDraftObservationExtractionWorkResult,
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


def _now() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _document_ref() -> SourceDocumentRef:
    return SourceDocumentRef("source-document:project-1:abc")


def _source_unit(
    *,
    unit_ref: str,
    ordinal: int,
    document_ref: SourceDocumentRef | None = None,
) -> SourceUnit:
    return SourceUnit(
        unit_ref=SourceUnitRef(unit_ref),
        document_ref=document_ref or _document_ref(),
        unit_kind=SourceUnitKind.SECTION,
        text=SourceUnitText(f"# Unit {ordinal}\n\nBody"),
        heading_path=HeadingPath((f"Unit {ordinal}",)),
        lineage=SourceUnitLineage(),
        ordinal=ordinal,
        created_at=_now(),
    )


def _command(
    *,
    source_units: tuple[SourceUnit, ...],
    workflow_run_id: str = "knowledge-extraction:source-document:project-1:abc",
    source_document_ref: SourceDocumentRef | None = None,
) -> PlanDraftObservationExtractionWorkCommand:
    return PlanDraftObservationExtractionWorkCommand(
        workflow_run_id=workflow_run_id,
        source_document_ref=source_document_ref or _document_ref(),
        source_units=source_units,
    )


def test_creates_one_deterministic_plan_per_source_unit() -> None:
    first = _source_unit(
        unit_ref="source-document:project-1:abc.unit.0",
        ordinal=0,
    )
    second = _source_unit(
        unit_ref="source-document:project-1:abc.unit.1",
        ordinal=1,
    )
    command = _command(source_units=(second, first))

    result = PlanDraftObservationExtractionWork().execute(command)

    assert isinstance(result, PlanDraftObservationExtractionWorkResult)
    assert len(result.plans) == 2
    assert tuple(plan.source_unit_ordinal for plan in result.plans) == (0, 1)
    assert tuple(plan.source_unit_ref for plan in result.plans) == (
        first.unit_ref,
        second.unit_ref,
    )

    for plan in result.plans:
        assert isinstance(plan, DraftObservationExtractionWorkPlan)
        assert (
            plan.work_kind.value == "knowledge_workbench.draft_observation_extraction"
        )
        assert command.workflow_run_id in plan.work_item_id
        assert plan.source_unit_ref.value in plan.work_item_id
        assert plan.idempotency_key == plan.work_item_id


def test_repeated_execution_returns_identical_plans() -> None:
    source_units = (
        _source_unit(
            unit_ref="source-document:project-1:abc.unit.1",
            ordinal=1,
        ),
        _source_unit(
            unit_ref="source-document:project-1:abc.unit.0",
            ordinal=0,
        ),
    )
    command = _command(source_units=source_units)
    use_case = PlanDraftObservationExtractionWork()

    first = use_case.execute(command)
    second = use_case.execute(command)

    assert first == second


def test_duplicate_source_unit_refs_are_rejected() -> None:
    duplicate_ref = "source-document:project-1:abc.unit.0"

    with pytest.raises(ValueError, match="source_unit_ref must be unique"):
        _command(
            source_units=(
                _source_unit(unit_ref=duplicate_ref, ordinal=0),
                _source_unit(unit_ref=duplicate_ref, ordinal=1),
            ),
        )


def test_empty_source_units_returns_empty_plans() -> None:
    result = PlanDraftObservationExtractionWork().execute(
        _command(source_units=()),
    )

    assert result.plans == ()


def test_invalid_workflow_run_id_is_rejected() -> None:
    with pytest.raises(ValueError, match="workflow_run_id must be non-empty"):
        _command(source_units=(), workflow_run_id="  ")


def test_source_unit_document_ref_mismatch_is_rejected() -> None:
    with pytest.raises(ValueError, match="source_units must belong"):
        _command(
            source_units=(
                _source_unit(
                    unit_ref="source-document:project-2:def.unit.0",
                    ordinal=0,
                    document_ref=SourceDocumentRef("source-document:project-2:def"),
                ),
            ),
        )


def test_plan_draft_observation_extraction_work_source_guard() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/application/sagas/"
        "plan_draft_observation_extraction_work.py",
    ).read_text(encoding="utf-8")

    required_markers = (
        "PlanDraftObservationExtractionWork",
        "PlanDraftObservationExtractionWorkCommand",
        "PlanDraftObservationExtractionWorkResult",
        "DraftObservationExtractionWorkPlan",
        "knowledge_workbench.draft_observation_extraction",
        "idempotency_key",
        "WorkKind",
    )
    forbidden_markers = (
        "capacity_runtime",
        "llm_runtime",
        "artifact_runtime",
        "execution_runtime.application",
        "execution_runtime.infrastructure",
        "Postgres",
        "asyncpg",
        "queue",
        "worker",
        "lease",
        "LLM",
        "Groq",
        "qwen",
        "PROMPT_A_WORK_SCHEDULED",
        "DraftObservationExtractionSchedulingReconciler",
    )

    for marker in required_markers:
        assert marker in source

    for marker in forbidden_markers:
        assert marker not in source
