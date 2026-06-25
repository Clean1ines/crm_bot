from __future__ import annotations

import pytest

from src.contexts.llm_runtime.domain.routing.phase_route_policy import (
    PhaseRouteActivationScope,
    PhaseRouteKind,
    PhaseRoutePolicy,
    PhaseRouteReason,
    PhaseRouteRule,
)


def test_phase_route_policy_keeps_primary_fallback_manual_and_special_routes() -> None:
    policy = PhaseRoutePolicy(
        phase="CLAIM_BUILDER_SECTION_EXTRACTION",
        work_kind="knowledge_workbench.claim_builder.section_extraction",
        routes=(
            PhaseRouteRule(
                route_ref="claim_builder:primary:qwen",
                route_kind=PhaseRouteKind.PRIMARY,
                route_reason=PhaseRouteReason.NORMAL,
                model_ref="qwen/qwen3-32b",
                activation_scope=PhaseRouteActivationScope.PHASE,
            ),
            PhaseRouteRule(
                route_ref="claim_builder:auto:llama-versatile",
                route_kind=PhaseRouteKind.AUTOMATIC_FALLBACK,
                route_reason=PhaseRouteReason.DAILY_LIMIT_EXHAUSTED,
                model_ref="llama-3.3-70b-versatile",
                activation_scope=PhaseRouteActivationScope.PHASE,
            ),
            PhaseRouteRule(
                route_ref="claim_builder:manual:llama-instant",
                route_kind=PhaseRouteKind.MANUAL_FALLBACK,
                route_reason=PhaseRouteReason.USER_CONFIRMED_DEGRADED,
                model_ref="llama-3.1-8b-instant",
                activation_scope=PhaseRouteActivationScope.PHASE,
                requires_user_confirmation=True,
            ),
            PhaseRouteRule(
                route_ref="claim_builder:special:empty-claims:gpt-oss",
                route_kind=PhaseRouteKind.SPECIAL,
                route_reason=PhaseRouteReason.EMPTY_CLAIMS_VALIDATION,
                model_ref="openai/gpt-oss-120b",
                activation_scope=PhaseRouteActivationScope.WORK_ITEM,
            ),
        ),
    )

    assert policy.primary_route().model_ref == "qwen/qwen3-32b"
    assert len(policy.automatic_fallback_routes()) == 1
    assert len(policy.manual_fallback_routes()) == 1
    assert (
        policy.special_routes_for_reason(PhaseRouteReason.EMPTY_CLAIMS_VALIDATION)[
            0
        ].model_ref
        == "openai/gpt-oss-120b"
    )


def test_manual_fallback_requires_user_confirmation() -> None:
    with pytest.raises(ValueError, match="manual fallback routes"):
        PhaseRouteRule(
            route_ref="claim_builder:manual:llama-instant",
            route_kind=PhaseRouteKind.MANUAL_FALLBACK,
            route_reason=PhaseRouteReason.USER_CONFIRMED_DEGRADED,
            model_ref="llama-3.1-8b-instant",
            activation_scope=PhaseRouteActivationScope.PHASE,
        )


def test_policy_requires_exactly_one_primary_route() -> None:
    with pytest.raises(ValueError, match="exactly one primary"):
        PhaseRoutePolicy(
            phase="DRAFT_CLAIM_CLUSTERING",
            work_kind="knowledge_workbench.draft_claim_compaction",
            routes=(
                PhaseRouteRule(
                    route_ref="compaction:manual:llama-versatile",
                    route_kind=PhaseRouteKind.MANUAL_FALLBACK,
                    route_reason=PhaseRouteReason.USER_CONFIRMED_DEGRADED,
                    model_ref="llama-3.3-70b-versatile",
                    activation_scope=PhaseRouteActivationScope.PHASE,
                    requires_user_confirmation=True,
                ),
            ),
        )
