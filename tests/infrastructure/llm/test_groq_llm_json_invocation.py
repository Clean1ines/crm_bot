from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.domain.project_plane.llm_routing import (
    LlmInvocationStatus,
    LlmJsonInvocationRequest,
    LlmRouteAttemptStatus,
)
from src.infrastructure.llm.groq_llm_json_invocation import (
    GroqLlmJsonInvocationAdapter,
    GroqLlmJsonInvocationConfig,
)


@dataclass(frozen=True, slots=True)
class FakeUsage:
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int


@dataclass(frozen=True, slots=True)
class FakeMessage:
    content: str | None


@dataclass(frozen=True, slots=True)
class FakeChoice:
    message: FakeMessage


@dataclass(frozen=True, slots=True)
class FakeResponse:
    choices: tuple[FakeChoice, ...]
    usage: FakeUsage | None
    model: str | None


@dataclass(slots=True)
class FakeCompletions:
    response: FakeResponse
    captured_kwargs: dict[str, object] | None = None
    error: BaseException | None = None

    async def create(self, **kwargs: object) -> FakeResponse:
        self.captured_kwargs = dict(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


@dataclass(slots=True)
class FakeChat:
    completions: FakeCompletions


@dataclass(slots=True)
class FakeGroqClient:
    chat: FakeChat
    events: list[dict[str, object]] = field(default_factory=list)

    def route_observability_snapshot(self) -> dict[str, object]:
        return {"groq_route_events": self.events}


def _request() -> LlmJsonInvocationRequest:
    return LlmJsonInvocationRequest(
        operation_name="faq_surface_claim_observations",
        prompt="Return JSON",
        route_purpose="workbench_claim_observations",
    )


def _adapter(
    *,
    content: str = '{"findings":[]}',
    events: list[dict[str, object]] | None = None,
    error: BaseException | None = None,
) -> tuple[GroqLlmJsonInvocationAdapter, FakeCompletions]:
    completions = FakeCompletions(
        response=FakeResponse(
            choices=(FakeChoice(message=FakeMessage(content=content)),),
            usage=FakeUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
            model="llama-3.1-8b-instant",
        ),
        error=error,
    )
    default_events = [
        {
            "status": "failed" if error is not None else "success",
            "routed_model": "llama-3.1-8b-instant",
            "key_slot_label": "1/3",
            "limit_kind": "none" if error is not None else "",
        }
    ]
    client = FakeGroqClient(
        chat=FakeChat(completions=completions),
        events=events if events is not None else default_events,
    )
    return (
        GroqLlmJsonInvocationAdapter(
            client=client,
            config=GroqLlmJsonInvocationConfig(max_completion_tokens=1024),
        ),
        completions,
    )


@pytest.mark.asyncio
async def test_groq_adapter_invokes_rotating_client_with_json_response_format() -> None:
    adapter, completions = _adapter()

    result = await adapter.invoke_json(_request())

    assert result.status is LlmInvocationStatus.SUCCESS
    assert result.parsed_json == {"findings": []}
    assert result.token_usage.prompt_tokens == 10
    assert result.token_usage.completion_tokens == 5
    assert result.token_usage.total_tokens == 15
    assert result.attempts[0].provider_id == "groq"
    assert result.attempts[0].api_key_slot == "1/3"
    assert result.attempts[0].status is LlmRouteAttemptStatus.SUCCESS

    assert completions.captured_kwargs is not None
    assert completions.captured_kwargs["model"] == "llama-3.1-8b-instant"
    assert completions.captured_kwargs["temperature"] == 0.0
    assert completions.captured_kwargs["response_format"] == {"type": "json_object"}
    assert completions.captured_kwargs["max_completion_tokens"] == 1024


@pytest.mark.asyncio
async def test_groq_adapter_returns_invalid_json_failure() -> None:
    adapter, _completions = _adapter(content="not json")

    result = await adapter.invoke_json(_request())

    assert result.status is LlmInvocationStatus.INVALID_JSON
    assert result.failure is not None
    assert result.failure.error_kind == "invalid_json"
    assert result.parsed_json is None


@pytest.mark.asyncio
async def test_groq_adapter_maps_generic_provider_error() -> None:
    adapter, _completions = _adapter(error=RuntimeError("provider exploded"))

    result = await adapter.invoke_json(_request())

    assert result.status is LlmInvocationStatus.PROVIDER_ERROR
    assert result.failure is not None
    assert result.failure.error_kind == "none"
    assert result.attempts[0].status is LlmRouteAttemptStatus.FAILED


@pytest.mark.asyncio
async def test_groq_adapter_preserves_route_events_as_attempts() -> None:
    adapter, _completions = _adapter(
        events=[
            {
                "status": "failed",
                "routed_model": "llama-3.1-8b-instant",
                "key_slot_label": "1/3",
                "limit_kind": "tpm",
                "retry_after_seconds": 12.5,
            },
            {
                "status": "success",
                "routed_model": "qwen/qwen3-32b",
                "key_slot_label": "2/3",
                "limit_kind": "",
            },
        ]
    )

    result = await adapter.invoke_json(_request())

    assert result.status is LlmInvocationStatus.SUCCESS
    assert len(result.attempts) == 2
    assert result.attempts[0].model == "llama-3.1-8b-instant"
    assert result.attempts[0].error_kind == "tpm"
    assert result.attempts[0].cooldown_seconds == 12
    assert result.attempts[1].model == "qwen/qwen3-32b"
    assert result.attempts[1].status is LlmRouteAttemptStatus.SUCCESS
