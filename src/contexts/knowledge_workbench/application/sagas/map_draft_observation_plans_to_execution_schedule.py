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
            "provider_messages": _provider_messages(plan),
            "prompt_a_provenance": _prompt_a_provenance(plan),
        },
    )


def _provider_messages(
    plan: DraftObservationExtractionWorkPlan,
) -> tuple[dict[str, str], ...]:
    return (
        {
            "role": "system",
            "content": (
                "Extract draft claim observations as strict JSON. "
                "Use prompt_id faq_claim_observations and return only JSON."
            ),
        },
        {
            "role": "user",
            "content": (
                f"source_unit_ref: {plan.source_unit_ref.value}\n"
                f"heading_path: {_format_heading_path(plan.heading_path)}\n\n"
                f"{plan.source_unit_text}"
            ),
        },
    )


def _prompt_a_provenance(
    plan: DraftObservationExtractionWorkPlan,
) -> dict[str, str]:
    return {
        "workflow_run_id": plan.workflow_run_id,
        "stage_run_id": "draft_observation_extraction",
        "source_unit_ref": plan.source_unit_ref.value,
        "work_item_id": plan.work_item_id,
        "prompt_id": "faq_claim_observations",
        "prompt_version": "v1",
    }


def _format_heading_path(heading_path: tuple[str, ...]) -> str:
    if not heading_path:
        return "/"
    return " / ".join(heading_path)
