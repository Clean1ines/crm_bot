from __future__ import annotations

from src.contexts.llm_runtime.infrastructure.config.llm_runtime_provider_composition import (
    LlmRuntimeProviderCompositionFactory,
    LlmRuntimeProviderComponents,
)
from src.contexts.llm_runtime.infrastructure.config.llm_runtime_settings import (
    LlmRuntimeSettings,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_http_transport import (
    GroqHttpTransport,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_httpx_client import (
    GroqHttpxClient,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    GROQ_PROVIDER_ID,
)


def test_provider_composition_builds_groq_stack_from_llm_runtime_settings() -> None:
    components = LlmRuntimeProviderCompositionFactory(
        settings=LlmRuntimeSettings(
            groq_api_key="primary-secret",
            groq_api_key2="secondary-secret",
            groq_base_url="https://example.test/openai/v1",
            groq_timeout_seconds=12.5,
        ),
    ).build()

    assert isinstance(components, LlmRuntimeProviderComponents)
    assert [
        account.account_ref.value for account in components.groq.provider_accounts
    ] == [
        "groq_org_primary",
        "groq_org_secondary",
    ]
    assert all(
        account.provider_id == GROQ_PROVIDER_ID
        for account in components.groq.provider_accounts
    )

    assert components.groq.model_profiles
    assert components.groq.provider.model_profiles == components.groq.model_profiles
    assert isinstance(components.groq.provider.transport, GroqHttpTransport)
    assert isinstance(components.groq.provider.transport.http_client, GroqHttpxClient)
    assert (
        components.groq.provider.transport.base_url == "https://example.test/openai/v1"
    )
    assert components.groq.provider.transport.timeout_seconds == 12.5


def test_provider_composition_uses_primary_key_for_primary_transport() -> None:
    components = LlmRuntimeProviderCompositionFactory(
        settings=LlmRuntimeSettings(
            groq_api_key="primary-secret",
            groq_api_key2="secondary-secret",
        ),
    ).build()

    transport = components.groq.provider.transport

    assert isinstance(transport, GroqHttpTransport)
    assert transport.api_key.value == "primary-secret"
