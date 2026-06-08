from __future__ import annotations

from dataclasses import dataclass

from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_env_config import (
    GroqEnvConfig,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_http_transport import (
    GroqHttpClientPort,
    GroqHttpTransport,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_provider_adapter import (
    GroqProviderAdapter,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_provider_composition import (
    GroqProviderRuntimeComponents,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    build_groq_free_plan_model_profiles,
    build_groq_provider_accounts,
)


@dataclass(frozen=True, slots=True)
class GroqHttpProviderRuntimeFactory:
    """Compose Groq provider runtime using real HTTP transport objects.

    This factory still does not create an HTTP client itself and does not read
    env. It receives resolved config and a client port explicitly.
    """

    http_client: GroqHttpClientPort
    env_config: GroqEnvConfig
    model_profiles: tuple[ModelProfile, ...] | None = None
    base_url: str = "https://api.groq.com/openai/v1"
    timeout_seconds: float = 60.0

    def build_primary(self) -> GroqProviderRuntimeComponents:
        model_profiles = self.model_profiles or build_groq_free_plan_model_profiles()
        primary = self.env_config.accounts[0]
        provider_accounts = build_groq_provider_accounts(
            tuple(account.account_seed for account in self.env_config.accounts),
        )

        return GroqProviderRuntimeComponents(
            provider=GroqProviderAdapter(
                transport=GroqHttpTransport(
                    http_client=self.http_client,
                    api_key=primary.api_key,
                    base_url=self.base_url,
                    timeout_seconds=self.timeout_seconds,
                ),
                model_profiles=model_profiles,
            ),
            model_profiles=model_profiles,
            provider_accounts=provider_accounts,
        )
