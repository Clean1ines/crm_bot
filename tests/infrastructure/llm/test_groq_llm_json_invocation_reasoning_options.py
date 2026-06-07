from __future__ import annotations

from dataclasses import dataclass, field
from typing import cast

import pytest

from src.domain.project_plane.llm_routing import (
    LlmInvocationStatus,
    LlmJsonInvocationRequest,
)
from src.infrastructure.llm.groq_llm_json_invocation import (
    GroqJsonClientLike,
    GroqLlmJsonInvocationAdapter,
    GroqLlmJsonInvocationConfig,
)


@dataclass(frozen=True, slots=True)
class FakeUsage:
    prompt_tokens: int = 1
    completion_tokens: int = 2
    total_tokens: int = 3


@dataclass(frozen=True, slots=True)
class FakeMessage:
    content: str | None = '{"claim_observations":[]}'


@dataclass(frozen=True, slots=True)
class FakeChoice:
    message: FakeMessage = FakeMessage()


@dataclass(frozen=True, slots=True)
class FakeResponse:
    choices: tuple[FakeChoice, ...] = (FakeChoice(),)
    usage: FakeUsage | None = FakeUsage()
    model: str | None = "qwen/qwen3-32b"


@dataclass(slots=True)
class FakeCompletions:
    captured_kwargs: dict[str, object] = field(default_factory=dict)

    async def create(self, **kwargs: object) -> FakeResponse:
        self.captured_kwargs.clear()
        self.captured_kwargs.update(kwargs)
        return FakeResponse()


@dataclass(slots=True)
class FakeChat:
    completions: FakeCompletions


@dataclass(slots=True)
class FakeGroqClient:
    completions: FakeCompletions = field(default_factory=FakeCompletions)

    @property
    def chat(self) -> FakeChat:
        return FakeChat(completions=self.completions)

    def route_observability_snapshot(self) -> dict[str, object]:
        return {}


@pytest.mark.asyncio
async def test_groq_json_adapter_passes_reasoning_kwargs_when_configured() -> None:
    client = FakeGroqClient()
    adapter = GroqLlmJsonInvocationAdapter(
        client=cast(GroqJsonClientLike, client),
        config=GroqLlmJsonInvocationConfig(
            max_completion_tokens=None,
            reasoning_effort="none",
            reasoning_format="hidden",
        ),
    )

    result = await adapter.invoke_json(
        LlmJsonInvocationRequest(
            operation_name="test",
            prompt="return json",
            route_purpose="test",
            idempotency_key="test-key",
        )
    )

    assert result.status is LlmInvocationStatus.SUCCESS
    assert client.completions.captured_kwargs["reasoning_effort"] == "none"
    assert client.completions.captured_kwargs["reasoning_format"] == "hidden"
    assert "max_completion_tokens" not in client.completions.captured_kwargs
