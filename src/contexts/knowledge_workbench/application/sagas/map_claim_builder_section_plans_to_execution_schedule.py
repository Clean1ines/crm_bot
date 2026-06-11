from __future__ import annotations

from dataclasses import dataclass

from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    WorkItemSchedulePlan,
)
from src.contexts.knowledge_workbench.application.sagas.plan_claim_builder_section_work import (
    ClaimBuilderSectionWorkPlan,
)


@dataclass(frozen=True, slots=True)
class MapClaimBuilderSectionPlansToExecutionScheduleCommand:
    plans: tuple[ClaimBuilderSectionWorkPlan, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.plans, tuple):
            raise TypeError("plans must be tuple")

        seen_work_item_ids: set[str] = set()
        for plan in self.plans:
            if not isinstance(plan, ClaimBuilderSectionWorkPlan):
                raise TypeError(
                    "plans must contain only ClaimBuilderSectionWorkPlan",
                )
            if plan.work_item_id in seen_work_item_ids:
                raise ValueError("work_item_id must be unique")
            seen_work_item_ids.add(plan.work_item_id)


@dataclass(frozen=True, slots=True)
class MapClaimBuilderSectionPlansToExecutionScheduleResult:
    schedule_plans: tuple[WorkItemSchedulePlan, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.schedule_plans, tuple):
            raise TypeError("schedule_plans must be tuple")
        for schedule_plan in self.schedule_plans:
            if not isinstance(schedule_plan, WorkItemSchedulePlan):
                raise TypeError("schedule_plans must contain only WorkItemSchedulePlan")


class MapClaimBuilderSectionPlansToExecutionSchedule:
    def execute(
        self,
        command: MapClaimBuilderSectionPlansToExecutionScheduleCommand,
    ) -> MapClaimBuilderSectionPlansToExecutionScheduleResult:
        schedule_plans = tuple(
            _map_plan_to_schedule_plan(plan) for plan in command.plans
        )
        return MapClaimBuilderSectionPlansToExecutionScheduleResult(
            schedule_plans=schedule_plans,
        )


def _map_plan_to_schedule_plan(
    plan: ClaimBuilderSectionWorkPlan,
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
            "phase": "claim_builder_section_extraction",
            "provider_messages": _provider_messages(plan),
            "claim_builder_provenance": _claim_builder_provenance(plan),
        },
    )


def _provider_messages(
    plan: ClaimBuilderSectionWorkPlan,
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


def _claim_builder_provenance(
    plan: ClaimBuilderSectionWorkPlan,
) -> dict[str, str]:
    return {
        "workflow_run_id": plan.workflow_run_id,
        "stage_run_id": "claim_builder_section_extraction",
        "source_unit_ref": plan.source_unit_ref.value,
        "work_item_id": plan.work_item_id,
        "prompt_id": "faq_claim_observations",
        "prompt_version": "v1",
    }


def _format_heading_path(heading_path: tuple[str, ...]) -> str:
    if not heading_path:
        return "/"
    return " / ".join(heading_path)
