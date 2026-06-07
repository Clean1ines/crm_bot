from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import cast

import pytest

from src.application.ai_playground.contracts import AiPlaygroundRunRequest
from src.application.ai_playground.run_ai_playground import (
    AiPlaygroundLlmResult,
    RunAiPlaygroundService,
)
from src.infrastructure.llm.groq_keyring import GroqClientRotator
from src.interfaces.composition.ai_playground import GroqAiPlaygroundAdapter


@dataclass(slots=True)
class FakeLlm:
    calls: list[AiPlaygroundRunRequest] = field(default_factory=list)

    async def run(self, request: AiPlaygroundRunRequest) -> AiPlaygroundLlmResult:
        self.calls.append(request)
        return AiPlaygroundLlmResult(raw_text="ok", model=request.model)


@dataclass(frozen=True, slots=True)
class FakeUsage:
    prompt_tokens: int = 1
    completion_tokens: int = 2
    total_tokens: int = 3


@dataclass(frozen=True, slots=True)
class FakeMessage:
    content: str | None = "ok"


@dataclass(frozen=True, slots=True)
class FakeChoice:
    message: FakeMessage = FakeMessage()


@dataclass(frozen=True, slots=True)
class FakeCompletion:
    choices: Sequence[FakeChoice] = (FakeChoice(),)
    usage: FakeUsage | None = FakeUsage()
    model: str | None = "qwen/qwen3-32b"


@dataclass(slots=True)
class FakeCompletions:
    captured_kwargs: dict[str, object]

    async def create(self, **kwargs: object) -> FakeCompletion:
        self.captured_kwargs.clear()
        self.captured_kwargs.update(kwargs)
        return FakeCompletion()


@dataclass(slots=True)
class FakeChat:
    completions: FakeCompletions


@dataclass(slots=True)
class FakeClient:
    chat: FakeChat


@dataclass(slots=True)
class FakeRotator:
    captured_kwargs: dict[str, object] = field(default_factory=dict)
    operation_name: str = ""

    async def run(
        self,
        operation: Callable[[object], Awaitable[object]],
        *,
        operation_name: str,
    ) -> object:
        self.operation_name = operation_name
        client = FakeClient(
            chat=FakeChat(completions=FakeCompletions(self.captured_kwargs))
        )
        return await operation(client)


@pytest.mark.asyncio
async def test_ai_playground_reasoning_options_reach_llm_request() -> None:
    llm = FakeLlm()
    service = RunAiPlaygroundService(llm=llm)

    await service.run(
        AiPlaygroundRunRequest(
            system_prompt=" system ",
            user_input=" input ",
            model="qwen/qwen3-32b",
            reasoning_effort="none",
            reasoning_format="hidden",
        )
    )

    assert len(llm.calls) == 1
    assert llm.calls[0].system_prompt == "system"
    assert llm.calls[0].user_input == "input"
    assert llm.calls[0].model == "qwen/qwen3-32b"
    assert llm.calls[0].reasoning_effort == "none"
    assert llm.calls[0].reasoning_format == "hidden"


@pytest.mark.asyncio
async def test_groq_ai_playground_adapter_passes_reasoning_options_only_when_present() -> (
    None
):
    rotator = FakeRotator()
    adapter = GroqAiPlaygroundAdapter(client=cast(GroqClientRotator, rotator))

    await adapter.run(
        AiPlaygroundRunRequest(
            system_prompt="system",
            user_input="input",
            model="qwen/qwen3-32b",
        )
    )

    assert rotator.operation_name == "ai_playground.run"
    assert "reasoning_effort" not in rotator.captured_kwargs
    assert "reasoning_format" not in rotator.captured_kwargs

    await adapter.run(
        AiPlaygroundRunRequest(
            system_prompt="system",
            user_input="input",
            model="qwen/qwen3-32b",
            reasoning_effort="none",
            reasoning_format="hidden",
        )
    )

    assert rotator.captured_kwargs["model"] == "qwen/qwen3-32b"
    assert rotator.captured_kwargs["reasoning_effort"] == "none"
    assert rotator.captured_kwargs["reasoning_format"] == "hidden"
