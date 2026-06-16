from __future__ import annotations

from dataclasses import dataclass

from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    WorkItemSchedulePlan,
)
from src.contexts.knowledge_workbench.document_segmentation.domain.segmentation_budget import (
    estimate_tokens_roughly,
)
from src.contexts.knowledge_workbench.application.sagas.plan_claim_builder_section_work import (
    ClaimBuilderSectionWorkPlan,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_section_extraction_prompt_contract import (
    BuildClaimBuilderSectionExtractionPrompt,
    ClaimBuilderSectionExtractionPromptContract,
    ClaimBuilderSectionExtractionPromptInput,
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
    def __init__(
        self,
        *,
        prompt_builder: BuildClaimBuilderSectionExtractionPrompt | None = None,
    ) -> None:
        self._prompt_builder = (
            BuildClaimBuilderSectionExtractionPrompt()
            if prompt_builder is None
            else prompt_builder
        )

    def execute(
        self,
        command: MapClaimBuilderSectionPlansToExecutionScheduleCommand,
    ) -> MapClaimBuilderSectionPlansToExecutionScheduleResult:
        schedule_plans = tuple(
            _map_plan_to_schedule_plan(
                plan=plan,
                prompt_builder=self._prompt_builder,
            )
            for plan in command.plans
        )
        return MapClaimBuilderSectionPlansToExecutionScheduleResult(
            schedule_plans=schedule_plans,
        )


def _map_plan_to_schedule_plan(
    *,
    plan: ClaimBuilderSectionWorkPlan,
    prompt_builder: BuildClaimBuilderSectionExtractionPrompt,
) -> WorkItemSchedulePlan:
    prompt_contract = prompt_builder.execute(
        ClaimBuilderSectionExtractionPromptInput(
            source_unit_ref=plan.source_unit_ref.value,
            heading_path=plan.heading_path,
            source_unit_text=plan.source_unit_text,
        ),
    )
    token_estimate = _claim_builder_token_estimate(
        plan=plan,
        prompt_contract=prompt_contract,
    )
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
            "provider_messages": prompt_contract.provider_messages,
            "llm_capacity_estimate": token_estimate,
            "claim_builder_provenance": _claim_builder_provenance(
                plan=plan,
                prompt_contract=prompt_contract,
            ),
        },
    )


def _claim_builder_token_estimate(
    *,
    plan: ClaimBuilderSectionWorkPlan,
    prompt_contract: ClaimBuilderSectionExtractionPromptContract,
) -> dict[str, object]:
    prompt_message_tokens = tuple(
        max(1, estimate_tokens_roughly(message["content"]))
        for message in prompt_contract.provider_messages
    )
    source_unit_token_count = max(1, estimate_tokens_roughly(plan.source_unit_text))
    estimated_input_tokens = sum(prompt_message_tokens)
    reserved_output_tokens = max(1024, min(4096, estimated_input_tokens))

    return {
        "estimator": "rough_char_div_4_actual_provider_messages",
        "prompt_message_tokens": prompt_message_tokens,
        "source_unit_token_count": source_unit_token_count,
        "estimated_input_tokens": estimated_input_tokens,
        "reserved_output_tokens": reserved_output_tokens,
        "estimated_total_tokens": estimated_input_tokens + reserved_output_tokens,
    }


def _claim_builder_provenance(
    *,
    plan: ClaimBuilderSectionWorkPlan,
    prompt_contract: ClaimBuilderSectionExtractionPromptContract,
) -> dict[str, str]:
    return {
        "workflow_run_id": plan.workflow_run_id,
        "stage_run_id": "claim_builder_section_extraction",
        "source_unit_ref": plan.source_unit_ref.value,
        "work_item_id": plan.work_item_id,
        "prompt_id": prompt_contract.prompt_id,
        "prompt_version": prompt_contract.prompt_version,
    }
