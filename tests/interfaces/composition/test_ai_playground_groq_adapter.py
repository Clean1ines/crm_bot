from __future__ import annotations

from types import SimpleNamespace

import pytest

from src.application.ai_playground.contracts import AiPlaygroundRunRequest
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    GroqAccountSeed,
    build_groq_free_plan_model_profiles,
    build_groq_provider_accounts,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_provider_adapter import (
    GroqProviderAdapter,
)
from src.interfaces.composition.ai_playground import GroqAiPlaygroundAdapter


class FakeGroqTransport:
    def __init__(self) -> None:
        self.payload: dict[str, object] | None = None

    def post_chat_completions(self, *, payload: dict[str, object]) -> SimpleNamespace:
        self.payload = dict(payload)
        return SimpleNamespace(
            status_code=200,
            headers={},
            body={
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "ok",
                        }
                    }
                ]
            },
        )


@pytest.mark.asyncio
async def test_legacy_reasoning_format_is_not_forwarded_to_gpt_oss() -> None:
    model_profiles = build_groq_free_plan_model_profiles()
    provider_accounts = build_groq_provider_accounts(
        (GroqAccountSeed(account_ref="groq_test", account_rank=0),)
    )
    transport = FakeGroqTransport()
    provider = GroqProviderAdapter(
        transport=transport,
        model_profiles=model_profiles,
    )
    adapter = GroqAiPlaygroundAdapter(
        provider=provider,
        model_profiles=model_profiles,
        provider_accounts=provider_accounts,
    )

    result = await adapter.run(
        AiPlaygroundRunRequest(
            system_prompt="system",
            user_input="hello",
            model="openai/gpt-oss-120b",
            reasoning_format="hidden",
        )
    )

    assert result.raw_text == "ok"
    assert transport.payload is not None
    assert transport.payload["include_reasoning"] is False
    assert transport.payload["reasoning_effort"] == "low"
    assert "reasoning_format" not in transport.payload
