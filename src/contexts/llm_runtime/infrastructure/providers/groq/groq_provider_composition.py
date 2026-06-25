from __future__ import annotations

from dataclasses import dataclass

from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile
from src.contexts.llm_runtime.domain.entities.provider_account import ProviderAccount
from src.contexts.llm_runtime.domain.routing.provider_capacity_windows import (
    CapacityScopePolicy,
    ProviderCapacityProfile,
    ProviderParallelismPolicy,
)
from src.contexts.llm_runtime.domain.value_objects.provider_id import ProviderId
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    GroqAccountSeed,
    build_groq_free_plan_model_profiles,
    build_groq_provider_accounts,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_provider_adapter import (
    GroqProviderAdapter,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_transport_port import (
    GroqTransportPort,
)


@dataclass(frozen=True, slots=True)
class GroqProviderRuntimeComponents:
    """Explicitly composed Groq runtime components.

    This is an infrastructure composition object, not a service locator and not
    a hidden global config. The caller still owns transport and account seed
    configuration.
    """

    provider: GroqProviderAdapter
    model_profiles: tuple[ModelProfile, ...]
    provider_accounts: tuple[ProviderAccount, ...]
    capacity_profile: ProviderCapacityProfile

    def __post_init__(self) -> None:
        if not self.model_profiles:
            raise ValueError("model_profiles must not be empty")
        if not self.provider_accounts:
            raise ValueError("provider_accounts must not be empty")


@dataclass(frozen=True, slots=True)
class GroqProviderRuntimeFactory:
    """Build Groq runtime components from explicit transport and account seeds."""

    transport: GroqTransportPort
    account_seeds: tuple[GroqAccountSeed, ...]
    model_profiles: tuple[ModelProfile, ...] | None = None

    def __post_init__(self) -> None:
        if not self.account_seeds:
            raise ValueError("account_seeds must not be empty")

    @staticmethod
    def _provider_id_from_models(
        model_profiles: tuple[ModelProfile, ...],
    ) -> ProviderId:
        if not model_profiles:
            raise ValueError("model_profiles must not be empty")
        provider_id = model_profiles[0].provider_id
        for model_profile in model_profiles:
            if model_profile.provider_id != provider_id:
                raise ValueError("model_profiles must belong to one provider")
        return provider_id

    def build(self) -> GroqProviderRuntimeComponents:
        model_profiles = self.model_profiles or build_groq_free_plan_model_profiles()
        provider_accounts = build_groq_provider_accounts(self.account_seeds)

        return GroqProviderRuntimeComponents(
            provider=GroqProviderAdapter(
                transport=self.transport,
                model_profiles=model_profiles,
            ),
            model_profiles=model_profiles,
            provider_accounts=provider_accounts,
            capacity_profile=build_groq_free_provider_capacity_profile(
                provider_accounts=provider_accounts,
                model_profiles=model_profiles,
            ),
        )


def build_groq_free_provider_capacity_profile(
    *,
    provider_accounts: tuple[ProviderAccount, ...],
    model_profiles: tuple[ModelProfile, ...],
) -> ProviderCapacityProfile:
    return ProviderCapacityProfile(
        provider_id=GroqProviderRuntimeFactory._provider_id_from_models(
            model_profiles,
        ),
        accounts=provider_accounts,
        model_profiles=model_profiles,
        capacity_scope_policy=CapacityScopePolicy.ACCOUNT_MODEL,
        parallelism_policy=ProviderParallelismPolicy.one_slot_per_account_model_route(),
    )
