from __future__ import annotations

from dataclasses import dataclass, field

import pytest

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
        "openai/gpt-oss-20b",
        "openai/gpt-oss-120b",
        "llama-3.3-70b-versatile",
    ]

    assert [account.account_ref.value for account in components.provider_accounts] == [
        "groq_org_primary",
        "groq_org_secondary",
    ]
    assert all(
        account.provider_id == GROQ_PROVIDER_ID
        for account in components.provider_accounts
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

    with pytest.raises(ValueError):
        GroqProviderRuntimeComponents(
            provider=adapter,
            model_profiles=(),
            provider_accounts=(),
        )
