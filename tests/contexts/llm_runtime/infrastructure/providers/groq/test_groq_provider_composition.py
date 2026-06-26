from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.contexts.knowledge_workbench.application.routing.knowledge_extraction_phase_route_policies import (
    claim_builder_groq_free_phase_route_policy,
)

from src.contexts.llm_runtime.domain.routing.provider_capacity_windows import (
    CapacityScopePolicy,
    ProviderCapacityExecutionWindowExpander,
    ProviderParallelismPolicyKind,
    RouteActivation,
)
from src.contexts.llm_runtime.domain.routing.phase_route_policy import PhaseRouteReason
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_chat_request_builder import (
    JsonValue,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    GROQ_PROVIDER_ID,
    GroqAccountSeed,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_provider_adapter import (
    GroqProviderAdapter,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_provider_composition import (
    GroqProviderRuntimeComponents,
    GroqProviderRuntimeFactory,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_transport_port import (
    GroqTransportResponse,
)


@dataclass(slots=True)
class FakeGroqTransport:
    captured_payloads: list[dict[str, JsonValue]] = field(default_factory=list)

    def post_chat_completions(
        self,
        *,
        payload: dict[str, JsonValue],
    ) -> GroqTransportResponse:
        self.captured_payloads.append(payload)
        return GroqTransportResponse(
            status_code=200,
            headers={},
            body={},
        )


def test_factory_builds_provider_models_and_accounts_from_explicit_seeds() -> None:
    transport = FakeGroqTransport()

    components = GroqProviderRuntimeFactory(
        transport=transport,
        account_seeds=(
            GroqAccountSeed(account_ref="groq_org_primary", account_rank=0),
            GroqAccountSeed(account_ref="groq_org_secondary", account_rank=1),
        ),
    ).build()

    assert isinstance(components.provider, GroqProviderAdapter)
    assert components.provider.transport is transport
    assert components.provider.model_profiles == components.model_profiles

    assert [profile.model_id.value for profile in components.model_profiles] == [
        "qwen/qwen3-32b",
        "llama-3.1-8b-instant",
        "llama-3.3-70b-versatile",
        "meta-llama/llama-4-scout-17b-16e-instruct",
        "openai/gpt-oss-120b",
    ]

    assert [account.account_ref.value for account in components.provider_accounts] == [
        "groq_org_primary",
        "groq_org_secondary",
    ]
    assert all(
        account.provider_id == GROQ_PROVIDER_ID
        for account in components.provider_accounts
    )

    assert components.capacity_profile.provider_id == GROQ_PROVIDER_ID
    assert components.capacity_profile.accounts == components.provider_accounts
    assert components.capacity_profile.model_profiles == components.model_profiles
    assert components.capacity_profile.capacity_scope_policy is (
        CapacityScopePolicy.ACCOUNT_MODEL
    )
    assert components.capacity_profile.parallelism_policy.kind is (
        ProviderParallelismPolicyKind.ONE_SLOT_PER_ACCOUNT_MODEL_ROUTE
    )


def test_factory_rejects_empty_account_seed_list() -> None:
    with pytest.raises(ValueError):
        GroqProviderRuntimeFactory(
            transport=FakeGroqTransport(),
            account_seeds=(),
        )


def test_components_reject_empty_models_or_accounts() -> None:
    transport = FakeGroqTransport()
    adapter = GroqProviderAdapter(
        transport=transport,
        model_profiles=(),
    )
    valid_capacity_profile = (
        GroqProviderRuntimeFactory(
            transport=transport,
            account_seeds=(GroqAccountSeed(account_ref="groq_org_1", account_rank=0),),
        )
        .build()
        .capacity_profile
    )

    with pytest.raises(ValueError):
        GroqProviderRuntimeComponents(
            provider=adapter,
            model_profiles=(),
            provider_accounts=(),
            capacity_profile=valid_capacity_profile,
        )


def test_capacity_profile_expands_claim_builder_primary_route_across_groq_accounts() -> (
    None
):
    components = GroqProviderRuntimeFactory(
        transport=FakeGroqTransport(),
        account_seeds=(
            GroqAccountSeed(account_ref="groq_org_1", account_rank=0),
            GroqAccountSeed(account_ref="groq_org_2", account_rank=1),
            GroqAccountSeed(account_ref="groq_org_3", account_rank=2),
            GroqAccountSeed(account_ref="groq_org_4", account_rank=3),
        ),
    ).build()
    policy = claim_builder_groq_free_phase_route_policy()

    windows = ProviderCapacityExecutionWindowExpander().expand_activation(
        provider_profile=components.capacity_profile,
        activation=RouteActivation.from_phase_route_rule(
            phase=policy.phase,
            work_kind=policy.work_kind,
            route=policy.primary_route(),
        ),
    )

    assert len(windows) == 4
    assert {window.model_id.value for window in windows} == {"qwen/qwen3-32b"}
    assert {window.account_ref.value for window in windows} == {
        "groq_org_1",
        "groq_org_2",
        "groq_org_3",
        "groq_org_4",
    }


def test_capacity_profile_expands_claim_builder_special_gpt_oss_route_without_replacing_primary() -> (
    None
):
    components = GroqProviderRuntimeFactory(
        transport=FakeGroqTransport(),
        account_seeds=(
            GroqAccountSeed(account_ref="groq_org_1", account_rank=0),
            GroqAccountSeed(account_ref="groq_org_2", account_rank=1),
            GroqAccountSeed(account_ref="groq_org_3", account_rank=2),
            GroqAccountSeed(account_ref="groq_org_4", account_rank=3),
        ),
    ).build()
    policy = claim_builder_groq_free_phase_route_policy()
    route_reason = PhaseRouteReason.EMPTY_CLAIMS_VALIDATION
    special_route = policy.special_routes_for_reason(route_reason)[0]

    primary_windows = ProviderCapacityExecutionWindowExpander().expand_activation(
        provider_profile=components.capacity_profile,
        activation=RouteActivation.from_phase_route_rule(
            phase=policy.phase,
            work_kind=policy.work_kind,
            route=policy.primary_route(),
        ),
    )
    special_windows = ProviderCapacityExecutionWindowExpander().expand_activation(
        provider_profile=components.capacity_profile,
        activation=RouteActivation.from_phase_route_rule(
            phase=policy.phase,
            work_kind=policy.work_kind,
            route=special_route,
            target_work_item_id="work-item-empty-claims-validation",
        ),
    )

    assert route_reason.value == "empty_claims_validation"
    assert len(primary_windows) == 4
    assert len(special_windows) == 4
    assert {window.model_id.value for window in primary_windows} == {"qwen/qwen3-32b"}
    assert {window.model_id.value for window in special_windows} == {
        "openai/gpt-oss-120b"
    }
    assert not (
        {window.window_key for window in primary_windows}
        & {window.window_key for window in special_windows}
    )
