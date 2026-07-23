from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_CEILING
import os

from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    WorkItemSchedulePlan,
)


from src.contexts.knowledge_workbench.application.sagas.plan_claim_builder_section_work import (
    ClaimBuilderSectionWorkPlan,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_section_extraction_prompt_contract import (
    BuildClaimBuilderSectionExtractionPrompt,
    ClaimBuilderSectionExtractionPromptContract,
    ClaimBuilderSectionExtractionPromptInput,
)
from src.contexts.knowledge_workbench.application.sagas.model_budget_profile import (
    model_budget_profile_for_ref,
)
from src.contexts.llm_runtime.application.capacity.llm_capacity_estimate_payload import (
    build_llm_capacity_estimate_payload,
)

CLAIM_BUILDER_DEFAULT_PROMPT_TOKENS = 3_008
CLAIM_BUILDER_PROMPT_TOKENS_ENV = "CLAIM_BUILDER_PROMPT_TOKENS"
CLAIM_BUILDER_INPUT_SAFETY_GAP_TOKENS = 100
CLAIM_BUILDER_MODEL_REF = "qwen/qwen3.6-27b"
CLAIM_BUILDER_PHASE = "claim_builder_section_extraction"


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
            "phase": CLAIM_BUILDER_PHASE,
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
    prompt_token_count = _claim_builder_prompt_tokens_from_env()
    model_profile = model_budget_profile_for_ref(CLAIM_BUILDER_MODEL_REF)
    user_message_content = _require_single_user_message_content(
        prompt_contract.provider_messages,
    )
    source_unit_token_count = _estimate_artifact_tokens_from_chars(
        char_count=len(user_message_content),
        model_char_to_token_multiplier=model_profile.model_char_to_token_multiplier,
    )
    input_tokens = prompt_token_count + source_unit_token_count
    planned_output_tokens = source_unit_token_count

    return build_llm_capacity_estimate_payload(
        model_profile=model_profile,
        phase=CLAIM_BUILDER_PHASE,
        operation="section_extraction",
        estimator=(
            f"measured_prompt_{prompt_token_count}_"
            f"source_char_div_{model_profile.model_char_to_token_multiplier}"
            "_conservative_section_output"
        ),
        prompt_tokens=prompt_token_count,
        artifact_tokens=source_unit_token_count,
        input_tokens=input_tokens,
        planned_output_tokens=planned_output_tokens,
        safety_gap_tokens=CLAIM_BUILDER_INPUT_SAFETY_GAP_TOKENS,
        metadata={
            "model_char_to_token_multiplier": str(
                model_profile.model_char_to_token_multiplier
            ),
        },
    )


def _require_single_user_message_content(
    provider_messages: tuple[dict[str, str], ...],
) -> str:
    user_contents = tuple(
        message["content"]
        for message in provider_messages
        if message.get("role") == "user"
    )
    if len(user_contents) != 1:
        raise ValueError(
            "claim-builder prompt contract must contain exactly one user message"
        )
    content = user_contents[0]
    if not isinstance(content, str) or not content.strip():
        raise ValueError("claim-builder user message content must be non-empty")
    return content


def _estimate_artifact_tokens_from_chars(
    *,
    char_count: int,
    model_char_to_token_multiplier: Decimal,
) -> int:
    if isinstance(char_count, bool) or not isinstance(char_count, int):
        raise TypeError("char_count must be int")
    if char_count < 0:
        raise ValueError("char_count must be >= 0")
    if model_char_to_token_multiplier <= 0:
        raise ValueError("model_char_to_token_multiplier must be > 0")
    if char_count == 0:
        return 1
    return max(
        1,
        int(
            (Decimal(char_count) / model_char_to_token_multiplier).to_integral_value(
                rounding=ROUND_CEILING,
            )
        ),
    )


def _claim_builder_prompt_tokens_from_env() -> int:
    raw_value = os.environ.get(CLAIM_BUILDER_PROMPT_TOKENS_ENV)
    if raw_value is None or not raw_value.strip():
        return CLAIM_BUILDER_DEFAULT_PROMPT_TOKENS
    try:
        prompt_tokens = int(raw_value)
    except ValueError as exc:
        raise ValueError(
            f"{CLAIM_BUILDER_PROMPT_TOKENS_ENV} must be an integer",
        ) from exc
    if prompt_tokens <= 0:
        raise ValueError(f"{CLAIM_BUILDER_PROMPT_TOKENS_ENV} must be > 0")
    return prompt_tokens


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
