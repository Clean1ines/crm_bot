from __future__ import annotations

from decimal import Decimal

import pytest

from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile
from src.contexts.llm_runtime.domain.entities.provider_account import ProviderAccount
from src.contexts.llm_runtime.domain.routing.phase_route_policy import (
    PhaseRouteActivationScope,
    PhaseRouteKind,
    PhaseRouteReason,
    PhaseRouteRule,
)
from src.contexts.llm_runtime.domain.routing.provider_capacity_windows import (
    CapacityScopePolicy,
    ProviderCapacityExecutionWindowExpander,
    ProviderCapacityProfile,
    ProviderParallelismPolicy,
    RouteActivation,
    RouteActivationStatus,
)
from src.contexts.llm_runtime.domain.value_objects.model_id import ModelId
from src.contexts.llm_runtime.domain.value_objects.model_lifecycle import ModelLifecycle
from src.contexts.llm_runtime.domain.value_objects.provider_account_ref import (
    ProviderAccountRef,
)
from src.contexts.llm_runtime.domain.value_objects.provider_id import ProviderId
from src.contexts.llm_runtime.domain.value_objects.rate_limit_profile import (
    RateLimitProfile,
)
from src.contexts.llm_runtime.domain.value_objects.reasoning_profile import (
    ReasoningProfile,
)
from src.contexts.llm_runtime.domain.value_objects.token_price import TokenPrice


def _account(provider_id: ProviderId, account_ref: str, rank: int) -> ProviderAccount:
    return ProviderAccount(
        provider_id=provider_id,
        account_ref=ProviderAccountRef(account_ref),
        account_rank=rank,
    )


def _model(provider_id: ProviderId, model_ref: str, rank: int) -> ModelProfile:
    return ModelProfile(
        provider_id=provider_id,
        model_id=ModelId(model_ref),
        lifecycle=ModelLifecycle.PRODUCTION,
        context_window_tokens=131_072,
        max_output_tokens=32_768,
        model_rank=rank,
        rate_limits=RateLimitProfile(
            requests_per_minute=30,
            requests_per_day=1_000,
            tokens_per_minute=6_000,
            tokens_per_day=500_000,
        ),
        token_price=TokenPrice(
            input_per_million=Decimal("0.1"),
            output_per_million=Decimal("0.2"),
        ),
        reasoning_profile=ReasoningProfile.unsupported(),
    )


def _route(model_ref: str) -> PhaseRouteRule:
    return PhaseRouteRule(
        route_ref=f"claim_builder:primary:{model_ref}",
        route_kind=PhaseRouteKind.PRIMARY,
        route_reason=PhaseRouteReason.NORMAL,
        model_ref=model_ref,
        activation_scope=PhaseRouteActivationScope.PHASE,
    )


def _activation(model_ref: str) -> RouteActivation:
    return RouteActivation.from_phase_route_rule(
        phase="CLAIM_BUILDER_SECTION_EXTRACTION",
        work_kind="knowledge_workbench.claim_builder.section_extraction",
        route=_route(model_ref),
    )


def test_groq_free_four_accounts_one_slot_expands_to_four_windows_and_four_scopes() -> (
    None
):
    provider_id = ProviderId("groq")
    model_ref = "qwen/qwen3-32b"
    profile = ProviderCapacityProfile(
        provider_id=provider_id,
        accounts=tuple(
            _account(provider_id, f"groq_org_{index}", index) for index in range(1, 5)
        ),
        model_profiles=(_model(provider_id, model_ref, 0),),
        capacity_scope_policy=CapacityScopePolicy.ACCOUNT_MODEL,
        parallelism_policy=ProviderParallelismPolicy.one_slot_per_account_model_route(),
    )

    windows = ProviderCapacityExecutionWindowExpander().expand_activation(
        provider_profile=profile,
        activation=_activation(model_ref),
    )

    assert len(windows) == 4
    assert len({window.execution_slot_key.value for window in windows}) == 4
    assert len({window.capacity_scope_key.value for window in windows}) == 4
    assert {window.model_id.value for window in windows} == {model_ref}


def test_groq_free_eight_accounts_one_slot_expands_to_eight_windows_and_eight_scopes() -> (
    None
):
    provider_id = ProviderId("groq")
    model_ref = "qwen/qwen3-32b"
    profile = ProviderCapacityProfile(
        provider_id=provider_id,
        accounts=tuple(
            _account(provider_id, f"groq_org_{index}", index) for index in range(1, 9)
        ),
        model_profiles=(_model(provider_id, model_ref, 0),),
        capacity_scope_policy=CapacityScopePolicy.ACCOUNT_MODEL,
        parallelism_policy=ProviderParallelismPolicy.one_slot_per_account_model_route(),
    )

    windows = ProviderCapacityExecutionWindowExpander().expand_activation(
        provider_profile=profile,
        activation=_activation(model_ref),
    )

    assert len(windows) == 8
    assert len({window.execution_slot_key.value for window in windows}) == 8
    assert len({window.capacity_scope_key.value for window in windows}) == 8


def test_deepseek_paid_one_account_sixteen_slots_expands_to_sixteen_windows_one_scope() -> (
    None
):
    provider_id = ProviderId("deepseek")
    model_ref = "deepseek-chat"
    profile = ProviderCapacityProfile(
        provider_id=provider_id,
        accounts=(_account(provider_id, "deepseek_main", 0),),
        model_profiles=(_model(provider_id, model_ref, 0),),
        capacity_scope_policy=CapacityScopePolicy.ACCOUNT,
        parallelism_policy=ProviderParallelismPolicy.fixed_slots_per_account_model_route(
            16,
        ),
    )

    windows = ProviderCapacityExecutionWindowExpander().expand_activation(
        provider_profile=profile,
        activation=_activation(model_ref),
    )

    assert len(windows) == 16
    assert len({window.execution_slot_key.value for window in windows}) == 16
    assert len({window.capacity_scope_key.value for window in windows}) == 1
    assert {window.capacity_scope_key.model_id for window in windows} == {None}


def test_special_route_opens_additional_windows_without_replacing_primary_route() -> (
    None
):
    provider_id = ProviderId("groq")
    primary_model_ref = "qwen/qwen3-32b"
    special_model_ref = "openai/gpt-oss-120b"
    profile = ProviderCapacityProfile(
        provider_id=provider_id,
        accounts=tuple(
            _account(provider_id, f"groq_org_{index}", index) for index in range(1, 5)
        ),
        model_profiles=(
            _model(provider_id, primary_model_ref, 0),
            _model(provider_id, special_model_ref, 1),
        ),
        capacity_scope_policy=CapacityScopePolicy.ACCOUNT_MODEL,
        parallelism_policy=ProviderParallelismPolicy.one_slot_per_account_model_route(),
    )

    primary_windows = ProviderCapacityExecutionWindowExpander().expand_activation(
        provider_profile=profile,
        activation=_activation(primary_model_ref),
    )
    special_windows = ProviderCapacityExecutionWindowExpander().expand_activation(
        provider_profile=profile,
        activation=RouteActivation.from_phase_route_rule(
            phase="CLAIM_BUILDER_SECTION_EXTRACTION",
            work_kind="knowledge_workbench.claim_builder.section_extraction",
            route=PhaseRouteRule(
                route_ref="claim_builder:special:input_too_large:gpt_oss",
                route_kind=PhaseRouteKind.SPECIAL,
                route_reason=PhaseRouteReason.INPUT_TOO_LARGE,
                model_ref=special_model_ref,
                activation_scope=PhaseRouteActivationScope.WORK_ITEM,
            ),
            target_work_item_id="work-item-oversized",
        ),
    )

    assert len(primary_windows) == 4
    assert len(special_windows) == 4
    assert {window.model_id.value for window in primary_windows} == {primary_model_ref}
    assert {window.model_id.value for window in special_windows} == {special_model_ref}
    assert not (
        {window.window_key for window in primary_windows}
        & {window.window_key for window in special_windows}
    )


def test_provider_profile_rejects_route_model_that_is_not_in_profile() -> None:
    provider_id = ProviderId("groq")
    profile = ProviderCapacityProfile(
        provider_id=provider_id,
        accounts=(_account(provider_id, "groq_org_1", 1),),
        model_profiles=(_model(provider_id, "qwen/qwen3-32b", 0),),
        capacity_scope_policy=CapacityScopePolicy.ACCOUNT_MODEL,
        parallelism_policy=ProviderParallelismPolicy.one_slot_per_account_model_route(),
    )

    with pytest.raises(
        ValueError, match="route activation model_ref is not in provider profile"
    ):
        ProviderCapacityExecutionWindowExpander().expand_route(
            provider_profile=profile,
            route=_route("openai/gpt-oss-120b"),
        )


def test_route_activation_requires_target_work_item_for_work_item_scope() -> None:
    with pytest.raises(ValueError, match="requires target_work_item_id"):
        RouteActivation.from_phase_route_rule(
            phase="CLAIM_BUILDER_SECTION_EXTRACTION",
            work_kind="knowledge_workbench.claim_builder.section_extraction",
            route=PhaseRouteRule(
                route_ref="claim_builder:special:input_too_large:gpt_oss",
                route_kind=PhaseRouteKind.SPECIAL,
                route_reason=PhaseRouteReason.INPUT_TOO_LARGE,
                model_ref="openai/gpt-oss-120b",
                activation_scope=PhaseRouteActivationScope.WORK_ITEM,
            ),
        )


def test_non_active_route_activation_does_not_expand_into_windows() -> None:
    with pytest.raises(ValueError, match="only active route activations"):
        RouteActivation.from_phase_route_rule(
            phase="CLAIM_BUILDER_SECTION_EXTRACTION",
            work_kind="knowledge_workbench.claim_builder.section_extraction",
            route=_route("qwen/qwen3-32b"),
            status=RouteActivationStatus.WAITING_CAPACITY,
        )
