from __future__ import annotations

from dataclasses import dataclass

from src.contexts.execution_runtime.application.ports.work_item_scheduling_unit_of_work_port import (
    WorkItemSchedulingUnitOfWorkPort,
)
from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    EnsureWorkItemsScheduled,
    EnsureWorkItemsScheduledCommand,
)
from src.contexts.knowledge_workbench.application.sagas.map_draft_observation_plans_to_execution_schedule import (
    MapDraftObservationPlansToExecutionSchedule,
    MapDraftObservationPlansToExecutionScheduleCommand,
)
from src.contexts.knowledge_workbench.application.sagas.plan_draft_observation_extraction_work import (
    PlanDraftObservationExtractionWork,
    PlanDraftObservationExtractionWorkCommand,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)


@dataclass(frozen=True, slots=True)
class ScheduleDraftObservationExtractionWorkCommand:
    workflow_run_id: str
    source_document_ref: SourceDocumentRef
    source_units: tuple[SourceUnit, ...]

    def __post_init__(self) -> None:
        _require_non_empty_text(self.workflow_run_id, field_name="workflow_run_id")
        if not isinstance(self.source_document_ref, SourceDocumentRef):
            raise TypeError("source_document_ref must be SourceDocumentRef")
        if not isinstance(self.source_units, tuple):
            raise TypeError("source_units must be tuple")
        for source_unit in self.source_units:
            if not isinstance(source_unit, SourceUnit):
                raise TypeError("source_units must contain only SourceUnit")


@dataclass(frozen=True, slots=True)
class ScheduleDraftObservationExtractionWorkResult:
    planned_count: int
    created_count: int
    already_exists_count: int
    conflict_count: int

    def __post_init__(self) -> None:
        for field_name, value in (
            ("planned_count", self.planned_count),
            ("created_count", self.created_count),
            ("already_exists_count", self.already_exists_count),
            ("conflict_count", self.conflict_count),
        ):
            if not isinstance(value, int):
                raise TypeError(f"{field_name} must be int")
            if value < 0:
                raise ValueError(f"{field_name} must be >= 0")

    @property
    def is_conflict_free(self) -> bool:
        return self.conflict_count == 0


@dataclass(frozen=True, slots=True)
class ScheduleDraftObservationExtractionWork:
    scheduling_unit_of_work: WorkItemSchedulingUnitOfWorkPort

    async def execute(
        self,
        command: ScheduleDraftObservationExtractionWorkCommand,
    ) -> ScheduleDraftObservationExtractionWorkResult:
        workbench_plans = PlanDraftObservationExtractionWork().execute(
            PlanDraftObservationExtractionWorkCommand(
                workflow_run_id=command.workflow_run_id,
                source_document_ref=command.source_document_ref,
                source_units=command.source_units,
            ),
        )
        execution_schedule = MapDraftObservationPlansToExecutionSchedule().execute(
            MapDraftObservationPlansToExecutionScheduleCommand(
                plans=workbench_plans.plans,
            ),
        )
        scheduling_result = await EnsureWorkItemsScheduled(
            unit_of_work=self.scheduling_unit_of_work,
        ).execute(
            EnsureWorkItemsScheduledCommand(
                plans=execution_schedule.schedule_plans,
            ),
        )

        return ScheduleDraftObservationExtractionWorkResult(
            planned_count=len(execution_schedule.schedule_plans),
            created_count=scheduling_result.created_count,
            already_exists_count=scheduling_result.already_exists_count,
            conflict_count=scheduling_result.conflict_count,
        )


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
