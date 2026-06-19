from __future__ import annotations

import os

from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutorPort,
)
from src.contexts.llm_runtime.infrastructure.composition.llm_runtime_provider_composition import (
    LlmRuntimeProviderCompositionFactory,
)
from src.contexts.llm_runtime.infrastructure.config.llm_runtime_settings import (
    LlmRuntimeSettings,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_dispatch_executor import (
    GroqDispatchExecutor,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_http_transport import (
    GroqHttpTransport,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_httpx_client import (
    GroqHttpxClient,
)


def make_llm_dispatch_executor() -> LlmDispatchExecutorPort:
    runtime_settings = LlmRuntimeSettings.from_env_mapping(os.environ)
    provider_components = LlmRuntimeProviderCompositionFactory(
        settings=runtime_settings,
    ).build()
    groq_components = provider_components.groq
    groq_env_config = runtime_settings.to_groq_env_config()
    http_client = GroqHttpxClient()
    transports_by_account_ref = {
        account.account_seed.account_ref: GroqHttpTransport(
            http_client=http_client,
            api_key=account.api_key,
            base_url=runtime_settings.groq_base_url,
            timeout_seconds=runtime_settings.groq_timeout_seconds,
        )
        for account in groq_env_config.accounts
    }
    primary_account_ref = groq_env_config.accounts[0].account_seed.account_ref
    return GroqDispatchExecutor(
        transport=transports_by_account_ref[primary_account_ref],
        transports_by_account_ref=transports_by_account_ref,
        model_profiles=groq_components.model_profiles,
    )
