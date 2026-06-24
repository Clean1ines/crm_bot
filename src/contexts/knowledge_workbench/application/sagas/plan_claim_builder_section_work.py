from __future__ import annotations

from dataclasses import dataclass

from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)

CLAIM_BUILDER_SECTION_WORK_KIND = WorkKind(
    "knowledge_workbench.claim_builder.section_extraction",
)


@dataclass(frozen=True, slots=True)
class ClaimBuilderSectionWorkPlan:
    workflow_run_id: str
    source_document_ref: SourceDocumentRef
    source_unit_ref: SourceUnitRef
    source_unit_ordinal: int
    source_unit_text: str
    heading_path: tuple[str, ...]
    work_item_id: str
    work_kind: WorkKind
    idempotency_key: str
    project_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        if self.project_id is not None:
            _require_non_empty_text(self.project_id, field_name="project_id")
        if not isinstance(self.source_document_ref, SourceDocumentRef):
            raise TypeError("source_document_ref must be SourceDocumentRef")
        if not isinstance(self.source_unit_ref, SourceUnitRef):
            raise TypeError("source_unit_ref must be SourceUnitRef")
        if not isinstance(self.source_unit_ordinal, int):
            raise TypeError("source_unit_ordinal must be int")
        if self.source_unit_ordinal < 0:
            raise ValueError("source_unit_ordinal must be >= 0")
        _require_non_empty_text(self.source_unit_text, field_name="source_unit_text")
        if not isinstance(self.heading_path, tuple):
            raise TypeError("heading_path must be tuple")
        for heading_part in self.heading_path:
            _require_non_empty_text(heading_part, field_name="heading_path")
        _require_non_empty_text(self.work_item_id, field_name="work_item_id")
        if not isinstance(self.work_kind, WorkKind):
            raise TypeError("work_kind must be WorkKind")
        _require_non_empty_text(self.idempotency_key, field_name="idempotency_key")


@dataclass(frozen=True, slots=True)
class PlanClaimBuilderSectionWorkCommand:
    workflow_run_id: str
    source_document_ref: SourceDocumentRef
    source_units: tuple[SourceUnit, ...]
    project_id: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        if self.project_id is not None:
            _require_non_empty_text(self.project_id, field_name="project_id")
        if not isinstance(self.source_document_ref, SourceDocumentRef):
            raise TypeError("source_document_ref must be SourceDocumentRef")
        if not isinstance(self.source_units, tuple):
            raise TypeError("source_units must be tuple")

        seen_unit_refs: set[SourceUnitRef] = set()
        for source_unit in self.source_units:
            if not isinstance(source_unit, SourceUnit):
                raise TypeError("source_units must contain only SourceUnit")
            if source_unit.document_ref != self.source_document_ref:
                raise ValueError("source_units must belong to source_document_ref")
            if source_unit.unit_ref in seen_unit_refs:
                raise ValueError("source_unit_ref must be unique")
            seen_unit_refs.add(source_unit.unit_ref)


@dataclass(frozen=True, slots=True)
class PlanClaimBuilderSectionWorkResult:
    plans: tuple[ClaimBuilderSectionWorkPlan, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.plans, tuple):
            raise TypeError("plans must be tuple")
        for plan in self.plans:
            if not isinstance(plan, ClaimBuilderSectionWorkPlan):
                raise TypeError(
                    "plans must contain only ClaimBuilderSectionWorkPlan",
                )


class PlanClaimBuilderSectionWork:
    def execute(
        self,
        command: PlanClaimBuilderSectionWorkCommand,
    ) -> PlanClaimBuilderSectionWorkResult:
        ordered_source_units = tuple(
            sorted(command.source_units, key=lambda source_unit: source_unit.ordinal),
        )
        plans = tuple(
            _build_plan(
                workflow_run_id=command.workflow_run_id,
                project_id=command.project_id,
                source_document_ref=command.source_document_ref,
                source_unit=source_unit,
            )
            for source_unit in ordered_source_units
        )
        return PlanClaimBuilderSectionWorkResult(plans=plans)


def _build_plan(
    *,
    workflow_run_id: str,
    project_id: str | None,
    source_document_ref: SourceDocumentRef,
    source_unit: SourceUnit,
) -> ClaimBuilderSectionWorkPlan:
    work_item_id = _claim_builder_section_work_item_id(
        workflow_run_id=workflow_run_id,
        source_unit_ref=source_unit.unit_ref,
    )
    return ClaimBuilderSectionWorkPlan(
        workflow_run_id=workflow_run_id,
        project_id=project_id,
        source_document_ref=source_document_ref,
        source_unit_ref=source_unit.unit_ref,
        source_unit_ordinal=source_unit.ordinal,
        source_unit_text=source_unit.text.value,
        heading_path=source_unit.heading_path.parts,
        work_item_id=work_item_id,
        work_kind=CLAIM_BUILDER_SECTION_WORK_KIND,
        idempotency_key=work_item_id,
    )


def _claim_builder_section_work_item_id(
    *,
    workflow_run_id: str,
    source_unit_ref: SourceUnitRef,
) -> str:
    return (
        "knowledge-workbench:claim-builder:section-extraction:"
        f"{workflow_run_id}:{source_unit_ref.value}"
    )


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
