from __future__ import annotations

from src.contexts.knowledge_workbench.application.sagas.capacity_admission_phase_mapping import (
    CLAIM_BUILDER_ADMISSION_PHASE_PROFILE,
    DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE,
)
from src.contexts.llm_runtime.domain.routing.phase_route_policy import (
    PhaseRouteActivationScope,
    PhaseRouteKind,
    PhaseRoutePolicy,
    PhaseRouteReason,
    PhaseRouteRule,
)


CLAIM_BUILDER_PRIMARY_QWEN_ROUTE_REF = "claim_builder:primary:qwen"
CLAIM_BUILDER_AUTO_LLAMA_VERSATILE_ROUTE_REF = (
    "claim_builder:auto_fallback:llama_versatile"
)
CLAIM_BUILDER_AUTO_LLAMA_SCOUT_ROUTE_REF = "claim_builder:auto_fallback:llama_scout"
CLAIM_BUILDER_MANUAL_LLAMA_INSTANT_ROUTE_REF = (
    "claim_builder:manual_fallback:llama_instant"
)
CLAIM_BUILDER_SPECIAL_EMPTY_CLAIMS_GPT_OSS_ROUTE_REF = (
    "claim_builder:special:empty_claims_validation:gpt_oss"
)
CLAIM_BUILDER_SPECIAL_INPUT_TOO_LARGE_GPT_OSS_ROUTE_REF = (
    "claim_builder:special:input_too_large:gpt_oss"
)
CLAIM_BUILDER_SPECIAL_OUTPUT_TOO_LARGE_GPT_OSS_ROUTE_REF = (
    "claim_builder:special:output_too_large:gpt_oss"
)
CLAIM_BUILDER_SPECIAL_TRUNCATED_JSON_GPT_OSS_ROUTE_REF = (
    "claim_builder:special:truncated_json:gpt_oss"
)

DRAFT_CLAIM_COMPACTION_PRIMARY_GPT_OSS_ROUTE_REF = (
    "draft_claim_compaction:primary:gpt_oss"
)
DRAFT_CLAIM_COMPACTION_MANUAL_LLAMA_VERSATILE_ROUTE_REF = (
    "draft_claim_compaction:manual_fallback:llama_versatile"
)

QWEN_32B_MODEL_REF = "qwen/qwen3-32b"
LLAMA_VERSATILE_MODEL_REF = "llama-3.3-70b-versatile"
LLAMA_SCOUT_MODEL_REF = "meta-llama/llama-4-scout-17b-16e-instruct"
LLAMA_INSTANT_MODEL_REF = "llama-3.1-8b-instant"
GPT_OSS_120B_MODEL_REF = "openai/gpt-oss-120b"


def claim_builder_groq_free_phase_route_policy() -> PhaseRoutePolicy:
    return PhaseRoutePolicy(
        phase=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.phase,
        work_kind=CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind,
        routes=(
            PhaseRouteRule(
                route_ref=CLAIM_BUILDER_PRIMARY_QWEN_ROUTE_REF,
                route_kind=PhaseRouteKind.PRIMARY,
                route_reason=PhaseRouteReason.NORMAL,
                model_ref=QWEN_32B_MODEL_REF,
                activation_scope=PhaseRouteActivationScope.PHASE,
            ),
            PhaseRouteRule(
                route_ref=CLAIM_BUILDER_AUTO_LLAMA_VERSATILE_ROUTE_REF,
                route_kind=PhaseRouteKind.AUTOMATIC_FALLBACK,
                route_reason=PhaseRouteReason.DAILY_LIMIT_EXHAUSTED,
                model_ref=LLAMA_VERSATILE_MODEL_REF,
                activation_scope=PhaseRouteActivationScope.PHASE,
            ),
            PhaseRouteRule(
                route_ref=CLAIM_BUILDER_AUTO_LLAMA_SCOUT_ROUTE_REF,
                route_kind=PhaseRouteKind.AUTOMATIC_FALLBACK,
                route_reason=PhaseRouteReason.DAILY_LIMIT_EXHAUSTED,
                model_ref=LLAMA_SCOUT_MODEL_REF,
                activation_scope=PhaseRouteActivationScope.PHASE,
            ),
            PhaseRouteRule(
                route_ref=CLAIM_BUILDER_MANUAL_LLAMA_INSTANT_ROUTE_REF,
                route_kind=PhaseRouteKind.MANUAL_FALLBACK,
                route_reason=PhaseRouteReason.USER_CONFIRMED_DEGRADED,
                model_ref=LLAMA_INSTANT_MODEL_REF,
                activation_scope=PhaseRouteActivationScope.PHASE,
                requires_user_confirmation=True,
            ),
            PhaseRouteRule(
                route_ref=CLAIM_BUILDER_SPECIAL_EMPTY_CLAIMS_GPT_OSS_ROUTE_REF,
                route_kind=PhaseRouteKind.SPECIAL,
                route_reason=PhaseRouteReason.EMPTY_CLAIMS_VALIDATION,
                model_ref=GPT_OSS_120B_MODEL_REF,
                activation_scope=PhaseRouteActivationScope.WORK_ITEM,
            ),
        ),
    )


def draft_claim_compaction_groq_free_phase_route_policy() -> PhaseRoutePolicy:
    return PhaseRoutePolicy(
        phase=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.phase,
        work_kind=DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.work_kind,
        routes=(
            PhaseRouteRule(
                route_ref=DRAFT_CLAIM_COMPACTION_PRIMARY_GPT_OSS_ROUTE_REF,
                route_kind=PhaseRouteKind.PRIMARY,
                route_reason=PhaseRouteReason.NORMAL,
                model_ref=GPT_OSS_120B_MODEL_REF,
                activation_scope=PhaseRouteActivationScope.PHASE,
            ),
            PhaseRouteRule(
                route_ref=DRAFT_CLAIM_COMPACTION_MANUAL_LLAMA_VERSATILE_ROUTE_REF,
                route_kind=PhaseRouteKind.MANUAL_FALLBACK,
                route_reason=PhaseRouteReason.USER_CONFIRMED_DEGRADED,
                model_ref=LLAMA_VERSATILE_MODEL_REF,
                activation_scope=PhaseRouteActivationScope.PHASE,
                requires_user_confirmation=True,
            ),
        ),
    )


def knowledge_extraction_groq_free_phase_route_policies() -> tuple[
    PhaseRoutePolicy,
    ...,
]:
    return (
        claim_builder_groq_free_phase_route_policy(),
        draft_claim_compaction_groq_free_phase_route_policy(),
    )


def knowledge_extraction_groq_free_phase_route_policy_for_work_kind(
    work_kind: str,
) -> PhaseRoutePolicy:
    _require_non_empty_text(work_kind, "work_kind")
    for policy in knowledge_extraction_groq_free_phase_route_policies():
        if policy.work_kind == work_kind:
            return policy
    raise ValueError(f"unsupported knowledge extraction route work_kind: {work_kind}")


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
