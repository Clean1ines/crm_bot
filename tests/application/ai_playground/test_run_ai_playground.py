from __future__ import annotations

import pytest

from src.application.ai_playground.contracts import AiPlaygroundRunRequest
from src.application.ai_playground.run_ai_playground import (
    AiPlaygroundLlmResult,
    AiPlaygroundValidationError,
    RunAiPlaygroundService,
)


class FakeLlm:
    def __init__(self, raw_text: str = '{"claims": []}') -> None:
        self.raw_text = raw_text
        self.calls: list[AiPlaygroundRunRequest] = []

    async def run(self, request: AiPlaygroundRunRequest) -> AiPlaygroundLlmResult:
        self.calls.append(request)
        return AiPlaygroundLlmResult(
            raw_text=self.raw_text,
            model=request.model,
            provider="groq",
            status="completed",
            prompt_tokens=10,
            completion_tokens=5,
            total_tokens=15,
        )


@pytest.mark.asyncio
async def test_empty_system_prompt_rejected() -> None:
    service = RunAiPlaygroundService(llm=FakeLlm())

    with pytest.raises(AiPlaygroundValidationError):
        await service.run(AiPlaygroundRunRequest(system_prompt=" ", user_input="text"))


@pytest.mark.asyncio
async def test_empty_user_input_rejected() -> None:
    service = RunAiPlaygroundService(llm=FakeLlm())

    with pytest.raises(AiPlaygroundValidationError):
        await service.run(
            AiPlaygroundRunRequest(system_prompt="system", user_input=" ")
        )


@pytest.mark.asyncio
async def test_too_long_prompt_rejected() -> None:
    service = RunAiPlaygroundService(llm=FakeLlm())

    with pytest.raises(AiPlaygroundValidationError):
        await service.run(
            AiPlaygroundRunRequest(system_prompt="x" * 20001, user_input="text")
        )


@pytest.mark.asyncio
async def test_too_long_input_rejected() -> None:
    service = RunAiPlaygroundService(llm=FakeLlm())

    with pytest.raises(AiPlaygroundValidationError):
        await service.run(
            AiPlaygroundRunRequest(system_prompt="system", user_input="x" * 20001)
        )


@pytest.mark.asyncio
async def test_model_outside_allowlist_rejected() -> None:
    service = RunAiPlaygroundService(llm=FakeLlm())

    with pytest.raises(AiPlaygroundValidationError):
        await service.run(
            AiPlaygroundRunRequest(
                system_prompt="system",
                user_input="text",
                model="not-a-model",
            )
        )


@pytest.mark.asyncio
async def test_tpm_limit_rejected_before_llm_call() -> None:
    llm = FakeLlm()
    service = RunAiPlaygroundService(llm=llm)

    with pytest.raises(AiPlaygroundValidationError) as exc:
        await service.run(
            AiPlaygroundRunRequest(
                system_prompt="x" * 20000,
                user_input="x" * 20000,
                model="llama-3.1-8b-instant",
            )
        )

    assert "Твоё сообщение:" in str(exc.value)
    assert "6000 TPM" in str(exc.value)
    assert llm.calls == []


@pytest.mark.asyncio
async def test_valid_json_response_parsed() -> None:
    llm = FakeLlm(raw_text='{"claims": []}')
    service = RunAiPlaygroundService(llm=llm)

    result = await service.run(
        AiPlaygroundRunRequest(
            system_prompt="system",
            user_input="text",
            response_format="json",
        )
    )

    assert result.parsed_json == {"claims": []}
    assert result.json_parse_error is None
    assert result.usage is not None
    assert result.usage.total_tokens == 15


@pytest.mark.asyncio
async def test_invalid_json_returns_parse_error_not_exception() -> None:
    llm = FakeLlm(raw_text='```json\n{"claims": []}\n```')
    service = RunAiPlaygroundService(llm=llm)

    result = await service.run(
        AiPlaygroundRunRequest(
            system_prompt="system",
            user_input="text",
            response_format="json",
        )
    )

    assert result.parsed_json is None
    assert result.json_parse_error is not None


@pytest.mark.asyncio
async def test_llm_called_once_with_expected_prompt_input_model() -> None:
    llm = FakeLlm()
    service = RunAiPlaygroundService(llm=llm)

    await service.run(
        AiPlaygroundRunRequest(
            system_prompt=" system ",
            user_input=" input ",
            model="qwen/qwen3-32b",
        )
    )

    assert len(llm.calls) == 1
    assert llm.calls[0].system_prompt == "system"
    assert llm.calls[0].user_input == "input"
    assert llm.calls[0].model == "qwen/qwen3-32b"
