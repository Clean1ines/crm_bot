from __future__ import annotations

from dataclasses import dataclass

from src.contexts.llm_runtime.infrastructure.config.llm_runtime_settings import (
    LlmRuntimeSettings,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_http_provider_composition import (
    GroqHttpProviderRuntimeFactory,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_httpx_client import (
    GroqHttpxClient,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_provider_composition import (
    GroqProviderRuntimeComponents,
)


@dataclass(frozen=True, slots=True)
class LlmRuntimeProviderComponents:
    """Top-level provider components owned by LLM Runtime infrastructure.

    This composition object is the clean boundary for constructing provider
    infrastructure from LLM Runtime settings. It does not import legacy app
    Settings and does not perform workflow orchestration.
    """

    groq: GroqProviderRuntimeComponents


@dataclass(frozen=True, slots=True)
class LlmRuntimeProviderCompositionFactory:
    settings: LlmRuntimeSettings

    def build(self) -> LlmRuntimeProviderComponents:
        groq_env_config = self.settings.to_groq_env_config()

        groq_components = GroqHttpProviderRuntimeFactory(
            http_client=GroqHttpxClient(),
            env_config=groq_env_config,
            base_url=self.settings.groq_base_url,
            timeout_seconds=self.settings.groq_timeout_seconds,
        ).build_primary()

        return LlmRuntimeProviderComponents(groq=groq_components)
