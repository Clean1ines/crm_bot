from __future__ import annotations

from dataclasses import dataclass

from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    WorkItemSchedulePlan,
)
from src.contexts.knowledge_workbench.application.sagas.plan_draft_observation_extraction_work import (
    DraftObservationExtractionWorkPlan,
)


@dataclass(frozen=True, slots=True)
class MapDraftObservationPlansToExecutionScheduleCommand:
    plans: tuple[DraftObservationExtractionWorkPlan, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.plans, tuple):
            raise TypeError("plans must be tuple")

        seen_work_item_ids: set[str] = set()
        for plan in self.plans:
            if not isinstance(plan, DraftObservationExtractionWorkPlan):
                raise TypeError(
                    "plans must contain only DraftObservationExtractionWorkPlan",
                )
            if plan.work_item_id in seen_work_item_ids:
                raise ValueError("work_item_id must be unique")
            seen_work_item_ids.add(plan.work_item_id)


@dataclass(frozen=True, slots=True)
class MapDraftObservationPlansToExecutionScheduleResult:
    schedule_plans: tuple[WorkItemSchedulePlan, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.schedule_plans, tuple):
            raise TypeError("schedule_plans must be tuple")
        for schedule_plan in self.schedule_plans:
            if not isinstance(schedule_plan, WorkItemSchedulePlan):
                raise TypeError("schedule_plans must contain only WorkItemSchedulePlan")


class MapDraftObservationPlansToExecutionSchedule:
    def execute(
        self,
        command: MapDraftObservationPlansToExecutionScheduleCommand,
    ) -> MapDraftObservationPlansToExecutionScheduleResult:
        schedule_plans = tuple(
            _map_plan_to_schedule_plan(plan) for plan in command.plans
        )
        return MapDraftObservationPlansToExecutionScheduleResult(
            schedule_plans=schedule_plans,
        )


def _map_plan_to_schedule_plan(
    plan: DraftObservationExtractionWorkPlan,
) -> WorkItemSchedulePlan:
    return WorkItemSchedulePlan(
        work_item_id=plan.work_item_id,
        work_kind=plan.work_kind,
        idempotency_key=plan.idempotency_key,
        payload={
            "workflow_run_id": plan.workflow_run_id,
            "source_document_ref": plan.source_document_ref.value,
            "source_unit_ref": plan.source_unit_ref.value,
            "source_unit_ordinal": plan.source_unit_ordinal,
            "phase": "draft_observation_extraction",
        },
    )
