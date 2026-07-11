from __future__ import annotations

from dataclasses import dataclass

from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    DueWorkItemRecord,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    LlmModelCapacityLimits,
    LlmModelExecutionSettings,
    LlmModelRoute,
    LlmModelRouteCatalog,
    LlmModelRouteRole,
)
from src.contexts.llm_runtime.domain.capacity.llm_provider_account_capacity import (
    LlmProviderAccountCapacity,
)
from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile


QUESTION_GENERATION_PROFILE_ID = "workbench_rag_eval.question_generation.real_due_batch"
ADJUDICATION_PROFILE_ID = "workbench_rag_eval.adjudication.real_due_batch"

WORKBENCH_RAG_EVAL_PRIMARY_MODEL_REF = "qwen/qwen3-32b"
WORKBENCH_RAG_EVAL_AUTOMATIC_FALLBACK_MODEL_REF = "openai/gpt-oss-120b"


def workbench_rag_eval_route_catalog() -> LlmModelRouteCatalog:
    reasoning_disabled = LlmModelExecutionSettings(reasoning_enabled=False)
    return LlmModelRouteCatalog(
        routes=(
            LlmModelRoute(
                model_ref=WORKBENCH_RAG_EVAL_PRIMARY_MODEL_REF,
                role=LlmModelRouteRole.PRIMARY,
                order=0,
                execution_settings=reasoning_disabled,
                capacity_limits=LlmModelCapacityLimits(
                    input_token_limit=6_000,
                    output_token_limit=8_192,
                ),
            ),
            LlmModelRoute(
                model_ref=WORKBENCH_RAG_EVAL_AUTOMATIC_FALLBACK_MODEL_REF,
                role=LlmModelRouteRole.AUTOMATIC_FALLBACK,
                order=1,
                execution_settings=reasoning_disabled,
                capacity_limits=LlmModelCapacityLimits(
                    input_token_limit=131_072,
                    output_token_limit=65_536,
                ),
            ),
        ),
        require_degraded_user_choice=False,
    )


@dataclass(frozen=True, slots=True)
class WorkbenchRagEvalDispatchPreparationBuilder:
    profile_id: str

    def route_catalog(
        self,
        *,
        default_catalog: LlmModelRouteCatalog,
    ) -> LlmModelRouteCatalog:
        if not isinstance(default_catalog, LlmModelRouteCatalog):
            raise TypeError("default_catalog must be LlmModelRouteCatalog")
        return workbench_rag_eval_route_catalog()

    def build_profile_from_due_work_items(
        self,
        due_work_items: tuple[DueWorkItemRecord, ...],
    ) -> LlmTaskCapacityProfile:
        if not due_work_items:
            raise ValueError("due_work_items must be non-empty")
        estimates = tuple(
            _estimate_from_payload(record.schedule_payload) for record in due_work_items
        )
        return LlmTaskCapacityProfile(
            profile_id=self.profile_id,
            estimated_prompt_tokens=max(
                estimate.input_tokens for estimate in estimates
            ),
            estimated_completion_tokens=max(
                estimate.required_window_tokens - estimate.input_tokens
                for estimate in estimates
            ),
            estimated_requests=1,
        )

    def build_account_capacities(
        self,
        *,
        active_model_ref: str,
        provider_account_refs: tuple[str, ...],
        model_profiles: tuple[ModelProfile, ...],
    ) -> tuple[LlmProviderAccountCapacity, ...]:
        _require_non_empty_text(active_model_ref, field_name="active_model_ref")
        if not provider_account_refs:
            raise ValueError("provider_account_refs must be non-empty")
        if active_model_ref not in {
            WORKBENCH_RAG_EVAL_PRIMARY_MODEL_REF,
            WORKBENCH_RAG_EVAL_AUTOMATIC_FALLBACK_MODEL_REF,
        }:
            raise ValueError(
                "RAG Eval dispatch attempted to use forbidden model route: "
                f"{active_model_ref}"
            )

        profile = _model_profile_for_ref(
            model_profiles=model_profiles,
            model_ref=active_model_ref,
        )
        limits = profile.rate_limits
        if (
            limits.requests_per_minute is None
            or limits.tokens_per_minute is None
            or limits.requests_per_day is None
            or limits.tokens_per_day is None
        ):
            raise ValueError("model rate limits must be configured")

        return tuple(
            LlmProviderAccountCapacity(
                provider="groq",
                account_ref=account_ref,
                model_ref=active_model_ref,
                remaining_minute_requests=limits.requests_per_minute,
                remaining_minute_tokens=limits.tokens_per_minute,
                remaining_daily_requests=limits.requests_per_day,
                remaining_daily_tokens=limits.tokens_per_day,
            )
            for account_ref in provider_account_refs
        )


@dataclass(frozen=True, slots=True)
class RagEvalAdjudicationDispatchPreparationBuilder(
    WorkbenchRagEvalDispatchPreparationBuilder
):
    pass


def make_question_generation_dispatch_preparation_builder() -> (
    WorkbenchRagEvalDispatchPreparationBuilder
):
    return WorkbenchRagEvalDispatchPreparationBuilder(
        profile_id=QUESTION_GENERATION_PROFILE_ID,
    )


def make_adjudication_dispatch_preparation_builder() -> (
    RagEvalAdjudicationDispatchPreparationBuilder
):
    return RagEvalAdjudicationDispatchPreparationBuilder(
        profile_id=ADJUDICATION_PROFILE_ID,
    )


@dataclass(frozen=True, slots=True)
class _CapacityEstimate:
    input_tokens: int
    required_window_tokens: int


def _estimate_from_payload(payload: object) -> _CapacityEstimate:
    if not isinstance(payload, dict):
        raise TypeError("schedule_payload must be dict")
    estimate = payload.get("llm_capacity_estimate")
    if not isinstance(estimate, dict):
        raise ValueError("schedule_payload.llm_capacity_estimate is required")

    input_tokens = _positive_int(estimate.get("input_tokens"), "input_tokens")
    required_window_tokens = _positive_int(
        estimate.get("required_window_tokens"),
        "required_window_tokens",
    )
    if required_window_tokens <= input_tokens:
        raise ValueError("required_window_tokens must be greater than input_tokens")

    return _CapacityEstimate(
        input_tokens=input_tokens,
        required_window_tokens=required_window_tokens,
    )


def _model_profile_for_ref(
    *,
    model_profiles: tuple[ModelProfile, ...],
    model_ref: str,
) -> ModelProfile:
    for profile in model_profiles:
        if profile.model_id.value == model_ref:
            return profile
    raise ValueError(f"No ModelProfile found for model_ref: {model_ref}")


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ValueError(f"{field_name} must be positive int")
    return value


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
