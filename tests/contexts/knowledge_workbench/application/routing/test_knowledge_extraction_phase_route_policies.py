from __future__ import annotations

import pytest

from src.contexts.knowledge_workbench.application.routing.knowledge_extraction_phase_route_policies import (
    GPT_OSS_120B_MODEL_REF,
    LLAMA_INSTANT_MODEL_REF,
    LLAMA_SCOUT_MODEL_REF,
    LLAMA_VERSATILE_MODEL_REF,
    QWEN_32B_MODEL_REF,
    claim_builder_groq_free_phase_route_policy,
    draft_claim_compaction_groq_free_phase_route_policy,
    knowledge_extraction_groq_free_phase_route_policies,
    knowledge_extraction_groq_free_phase_route_policy_for_work_kind,
)
from src.contexts.knowledge_workbench.application.sagas.capacity_admission_phase_mapping import (
    CLAIM_BUILDER_ADMISSION_PHASE_PROFILE,
    DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE,
)
from src.contexts.llm_runtime.domain.routing.phase_route_policy import (
    PhaseRouteActivationScope,
    PhaseRouteKind,
    PhaseRouteReason,
)


def test_claim_builder_groq_free_policy_uses_qwen_primary_and_two_auto_fallbacks() -> (
    None
):
    policy = claim_builder_groq_free_phase_route_policy()

    assert policy.phase == CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.phase
    assert policy.work_kind == CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind
    assert policy.primary_route().model_ref == QWEN_32B_MODEL_REF
    assert tuple(route.model_ref for route in policy.automatic_fallback_routes()) == (
        LLAMA_VERSATILE_MODEL_REF,
        LLAMA_SCOUT_MODEL_REF,
    )


def test_claim_builder_groq_free_policy_keeps_empty_claims_gpt_oss_as_only_special_route() -> (
    None
):
    policy = claim_builder_groq_free_phase_route_policy()

    assert GPT_OSS_120B_MODEL_REF not in tuple(
        route.model_ref for route in policy.automatic_fallback_routes()
    )

    actual_special_reasons = {
        route.route_reason
        for route in policy.routes
        if route.route_kind is PhaseRouteKind.SPECIAL
    }

    assert actual_special_reasons == {PhaseRouteReason.EMPTY_CLAIMS_VALIDATION}

    routes = policy.special_routes_for_reason(PhaseRouteReason.EMPTY_CLAIMS_VALIDATION)

    assert len(routes) == 1
    assert routes[0].model_ref == GPT_OSS_120B_MODEL_REF
    assert routes[0].activation_scope is PhaseRouteActivationScope.WORK_ITEM


def test_claim_builder_groq_free_policy_uses_llama_instant_as_manual_fallback() -> None:
    policy = claim_builder_groq_free_phase_route_policy()

    manual_routes = policy.manual_fallback_routes()

    assert len(manual_routes) == 1
    assert manual_routes[0].model_ref == LLAMA_INSTANT_MODEL_REF
    assert manual_routes[0].requires_user_confirmation is True
    assert manual_routes[0].route_reason is PhaseRouteReason.USER_CONFIRMED_DEGRADED


def test_draft_claim_compaction_groq_free_policy_uses_gpt_oss_primary_and_no_auto_fallbacks() -> (
    None
):
    policy = draft_claim_compaction_groq_free_phase_route_policy()

    assert policy.phase == DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.phase
    assert policy.work_kind == DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.work_kind
    assert policy.primary_route().model_ref == GPT_OSS_120B_MODEL_REF
    assert policy.automatic_fallback_routes() == ()


def test_draft_claim_compaction_groq_free_policy_uses_llama_versatile_as_manual_fallback() -> (
    None
):
    policy = draft_claim_compaction_groq_free_phase_route_policy()

    manual_routes = policy.manual_fallback_routes()

    assert len(manual_routes) == 1
    assert manual_routes[0].model_ref == LLAMA_VERSATILE_MODEL_REF
    assert manual_routes[0].requires_user_confirmation is True
    assert manual_routes[0].route_reason is PhaseRouteReason.USER_CONFIRMED_DEGRADED


def test_knowledge_extraction_phase_policy_registry_resolves_by_work_kind() -> None:
    policies = knowledge_extraction_groq_free_phase_route_policies()

    assert len(policies) == 2
    assert (
        knowledge_extraction_groq_free_phase_route_policy_for_work_kind(
            CLAIM_BUILDER_ADMISSION_PHASE_PROFILE.work_kind
        )
        == claim_builder_groq_free_phase_route_policy()
    )
    assert (
        knowledge_extraction_groq_free_phase_route_policy_for_work_kind(
            DRAFT_CLAIM_COMPACTION_ADMISSION_PHASE_PROFILE.work_kind
        )
        == draft_claim_compaction_groq_free_phase_route_policy()
    )


def test_knowledge_extraction_phase_policy_registry_rejects_unknown_work_kind() -> None:
    with pytest.raises(
        ValueError, match="unsupported knowledge extraction route work_kind"
    ):
        knowledge_extraction_groq_free_phase_route_policy_for_work_kind(
            "knowledge_workbench.unknown",
        )
