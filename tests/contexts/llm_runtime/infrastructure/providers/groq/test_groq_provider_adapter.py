from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.contexts.llm_runtime.application.ports.llm_provider_input import (
    LlmProviderInput,
    LlmProviderMessage,
    LlmProviderMessageRole,
)
from src.contexts.llm_runtime.application.ports.llm_provider_port import (
    LlmProviderFailure,
    LlmProviderSuccess,
)
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.value_objects.input_ref import LlmInputRef
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute
from src.contexts.llm_runtime.domain.value_objects.model_id import ModelId
from src.contexts.llm_runtime.domain.value_objects.output_contract_ref import (
    OutputContractRef,
)
from src.contexts.llm_runtime.domain.value_objects.prompt_version import PromptVersion
from src.contexts.llm_runtime.domain.value_objects.provider_account_ref import (
    ProviderAccountRef,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    GROQ_PROVIDER_ID,
    build_groq_free_plan_model_profiles,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_chat_request_builder import (
    JsonValue,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_provider_adapter import (
    GroqProviderAdapter,
    GroqProviderAdapterFactory,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_transport_port import (
    GroqTransportResponse,
)


@dataclass(slots=True)
class FakeGroqTransport:
    response: GroqTransportResponse
    captured_payloads: list[dict[str, JsonValue]] = field(default_factory=list)

    def post_chat_completions(
        self, *, payload: dict[str, JsonValue]
    ) -> GroqTransportResponse:
        self.captured_payloads.append(payload)
        return self.response


def _task() -> LlmTask:
    return LlmTask(
        task_id="task-1",
        prompt_id="generic_prompt",
        prompt_version=PromptVersion("v1"),
        input_ref=LlmInputRef("input-1"),
        output_contract_ref=OutputContractRef("contract-1"),
    )


def _route(model: str = "qwen/qwen3-32b") -> LlmRoute:
    return LlmRoute(
        provider_id=GROQ_PROVIDER_ID,
        model_id=ModelId(model),
        account_ref=ProviderAccountRef("groq_org_primary"),
    )


def _provider_input() -> LlmProviderInput:
    return LlmProviderInput(
        messages=(
            LlmProviderMessage(
                role=LlmProviderMessageRole.SYSTEM,
                content="You return JSON.",
            ),
            LlmProviderMessage(
                role=LlmProviderMessageRole.USER,
                content="Return JSON.",
            ),
        ),
    )


def test_groq_provider_adapter_builds_payload_and_maps_success() -> None:
    transport = FakeGroqTransport(
        response=GroqTransportResponse(
            status_code=200,
            headers={
                "x-ratelimit-remaining-requests": "999",
                "x-ratelimit-remaining-tokens": "5999",
            },
            body={
                "choices": [
                    {
                        "message": {
                            "content": '{"ok": true}',
                        },
                    },
                ],
                "usage": {
                    "prompt_tokens": 10,
                    "completion_tokens": 5,
                },
            },
        ),
    )
    adapter = GroqProviderAdapter(
        transport=transport,
        model_profiles=build_groq_free_plan_model_profiles(),
    )

    result = adapter.invoke(
        task=_task(),
        route=_route(),
        provider_input=_provider_input(),
    )

    assert isinstance(result, LlmProviderSuccess)
    assert result.raw_text == '{"ok": true}'
    assert result.usage is not None
    assert result.usage.input_tokens == 10
    assert result.usage.output_tokens == 5

    assert len(transport.captured_payloads) == 1
    payload = transport.captured_payloads[0]
    assert payload["model"] == "qwen/qwen3-32b"
    assert payload["response_format"] == {"type": "json_object"}
    assert payload["reasoning_effort"] == "none"
    assert payload["messages"] == [
        {"role": "system", "content": "You return JSON."},
        {"role": "user", "content": "Return JSON."},
    ]


def test_groq_provider_adapter_maps_failure_without_retry_logic() -> None:
    transport = FakeGroqTransport(
        response=GroqTransportResponse(
            status_code=429,
            headers={
                "retry-after": "2",
            },
            body={
                "error": {
                    "message": "Rate limit reached",
                },
            },
        ),
    )
    adapter = GroqProviderAdapter(
        transport=transport,
        model_profiles=build_groq_free_plan_model_profiles(),
    )

    result = adapter.invoke(
        task=_task(),
        route=_route(),
        provider_input=_provider_input(),
    )

    assert isinstance(result, LlmProviderFailure)
    assert result.error_kind is LlmErrorKind.MINUTE_LIMIT
    assert result.wait_until is not None


def test_groq_provider_adapter_requires_model_profile_for_route() -> None:
    transport = FakeGroqTransport(
        response=GroqTransportResponse(
            status_code=200,
            headers={},
            body={},
        ),
    )
    adapter = GroqProviderAdapter(
        transport=transport,
        model_profiles=build_groq_free_plan_model_profiles(),
    )

    with pytest.raises(ValueError):
        adapter.invoke(
            task=_task(),
            route=_route(model="missing-model"),
            provider_input=_provider_input(),
        )


def test_groq_provider_adapter_factory_does_not_hide_configuration() -> None:
    transport = FakeGroqTransport(
        response=GroqTransportResponse(
            status_code=200,
            headers={},
            body={},
        ),
    )

    adapter = GroqProviderAdapterFactory(
        transport=transport,
        model_profiles=build_groq_free_plan_model_profiles(),
    ).build()

    assert adapter.transport is transport
    assert adapter.model_profiles == build_groq_free_plan_model_profiles()
