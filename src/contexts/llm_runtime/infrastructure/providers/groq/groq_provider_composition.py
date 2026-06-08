from __future__ import annotations

from dataclasses import dataclass

from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile
from src.contexts.llm_runtime.domain.entities.provider_account import ProviderAccount
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
        )
