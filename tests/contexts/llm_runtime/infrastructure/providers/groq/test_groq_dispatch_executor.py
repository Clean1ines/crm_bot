from __future__ import annotations

from datetime import UTC, datetime

import pytest

from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionInput,
    LlmDispatchExecutionStatus,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_chat_request_builder import (
    JsonValue,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_dispatch_executor import (
    GroqDispatchExecutor,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_model_catalog_seed import (
    build_groq_free_plan_model_profiles,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_transport_port import (
    GroqTransportResponse,
)


class FakeGroqTransport:
    def __init__(self, response: GroqTransportResponse) -> None:
        self.response = response
        self.payloads: list[dict[str, JsonValue]] = []

    def post_chat_completions(
        self,
        *,
        payload: dict[str, JsonValue],
    ) -> GroqTransportResponse:
        self.payloads.append(payload)
        return self.response


def _started_at() -> datetime:
    return datetime(2026, 6, 11, 12, 0, tzinfo=UTC)


def _success_response(raw_text: str = '{"ok": true}') -> GroqTransportResponse:
    return GroqTransportResponse(
        status_code=200,
        headers={},
        body={
            "choices": [
                {
                    "message": {
                        "content": raw_text,
                    },
                },
            ],
            "usage": {
                "prompt_tokens": 7,
                "completion_tokens": 11,
            },
        },
    )


def _dispatch_payload(
    *,
    schedule_payload: dict[str, object] | None = None,
    execution_settings: dict[str, object] | None = None,
) -> dict[str, object]:
    return {
        "work_item_id": "work-1",
        "schedule_payload": schedule_payload
        if schedule_payload is not None
        else {
            "provider_messages": [
                {
                    "role": "user",
                    "content": "Extract claims",
                },
            ],
            "llm_capacity_estimate": {
                "estimated_input_tokens": 1000,
            },
        },
        "llm_allocation": {
            "provider": "groq",
            "account_ref": "groq_org_primary",
            "model_ref": "qwen/qwen3-32b",
            "slot_index": 0,
        },
        "llm_execution_settings": execution_settings
        if execution_settings is not None
        else {"reasoning_enabled": False},
    }


def _execution_input(
    *,
    dispatch_payload: dict[str, object] | None = None,
) -> LlmDispatchExecutionInput:
    return LlmDispatchExecutionInput(
        attempt_id="attempt-1",
        work_item_id="work-1",
        attempt_number=1,
        dispatch_payload=dispatch_payload or _dispatch_payload(),
        started_at=_started_at(),
    )


def _executor(transport: FakeGroqTransport) -> GroqDispatchExecutor:
    return GroqDispatchExecutor(
        transport=transport,
        model_profiles=build_groq_free_plan_model_profiles(),
    )


@pytest.mark.asyncio
async def test_builds_request_from_dispatch_payload_and_honors_qwen_reasoning_disabled() -> (
    None
):
    transport = FakeGroqTransport(response=_success_response(raw_text='{"done": true}'))

    result = await _executor(transport).execute_dispatch(_execution_input())

    assert result.status is LlmDispatchExecutionStatus.SUCCEEDED
    assert result.output_payload == {
        "raw_text": '{"done": true}',
        "provider": "groq",
        "model_ref": "qwen/qwen3-32b",
        "account_ref": "groq_org_primary",
        "usage": {
            "input_tokens": 7,
            "output_tokens": 11,
            "total_tokens": 18,
        },
    }
    assert len(transport.payloads) == 1
    request_payload = transport.payloads[0]
    assert request_payload["model"] == "qwen/qwen3-32b"
    assert request_payload["messages"] == [
        {
            "role": "user",
            "content": "Extract claims",
        },
    ]
    assert "reasoning_effort" not in request_payload


@pytest.mark.asyncio
async def test_prepared_request_output_cap_becomes_max_completion_tokens() -> None:
    schedule_payload = {
        "provider_messages": [
            {
                "role": "user",
                "content": "Extract claims",
            },
        ],
        "llm_capacity_estimate": {
            "estimated_input_tokens": 1000,
            "request_output_cap_tokens": 1234,
        },
    }
    transport = FakeGroqTransport(response=_success_response())

    result = await _executor(transport).execute_dispatch(
        _execution_input(
            dispatch_payload=_dispatch_payload(schedule_payload=schedule_payload),
        ),
    )

    assert result.status is LlmDispatchExecutionStatus.SUCCEEDED
    assert transport.payloads[0]["max_completion_tokens"] == 1234


@pytest.mark.asyncio
async def test_missing_prepared_request_output_cap_does_not_send_max_completion_tokens() -> (
    None
):
    schedule_payload = {
        "provider_messages": [
            {
                "role": "user",
                "content": "Extract claims",
            },
        ],
        "llm_capacity_estimate": {
            "estimated_input_tokens": 1000,
        },
    }
    transport = FakeGroqTransport(response=_success_response())

    result = await _executor(transport).execute_dispatch(
        _execution_input(
            dispatch_payload=_dispatch_payload(schedule_payload=schedule_payload),
        ),
    )

    assert result.status is LlmDispatchExecutionStatus.SUCCEEDED
    assert "max_completion_tokens" not in transport.payloads[0]


@pytest.mark.asyncio
async def test_invalid_dispatch_missing_provider_messages_returns_terminal_failed() -> (
    None
):
    transport = FakeGroqTransport(response=_success_response())

    result = await _executor(transport).execute_dispatch(
        _execution_input(dispatch_payload=_dispatch_payload(schedule_payload={})),
    )

    assert result.status is LlmDispatchExecutionStatus.TERMINAL_FAILED
    assert result.error_kind == "invalid_dispatch_payload"
    assert transport.payloads == []


@pytest.mark.asyncio
async def test_transport_mapper_retryable_error_maps_to_retryable_failed() -> None:
    transport = FakeGroqTransport(
        response=GroqTransportResponse(
            status_code=400,
            headers={},
            body={"error": {"message": "maximum context length exceeded"}},
        ),
    )

    result = await _executor(transport).execute_dispatch(_execution_input())

    assert result.status is LlmDispatchExecutionStatus.RETRYABLE_FAILED
    assert result.error_kind == "request_too_large"


@pytest.mark.asyncio
async def test_minute_limit_with_wait_until_maps_to_retryable_failed() -> None:
    transport = FakeGroqTransport(
        response=GroqTransportResponse(
            status_code=429,
            headers={"retry-after": "2"},
            body={"error": {"message": "Rate limit reached"}},
        ),
    )

    result = await _executor(transport).execute_dispatch(_execution_input())

    assert result.status is LlmDispatchExecutionStatus.RETRYABLE_FAILED
    assert result.error_kind == "minute_limit"
    assert not hasattr(result, "next" + "_attempt" + "_at")
    assert result.capacity_observation is not None
    assert result.capacity_observation["outcome_class"] == (
        LlmDispatchExecutionStatus.RETRYABLE_FAILED.value
    )


@pytest.mark.asyncio
async def test_capacity_observation_keeps_separate_minute_and_daily_resets() -> None:
    transport = FakeGroqTransport(
        response=GroqTransportResponse(
            status_code=200,
            headers={
                "x-ratelimit-remaining-requests": "900",
                "x-ratelimit-remaining-tokens": "4300",
                "x-ratelimit-reset-tokens": "35s",
                "x-ratelimit-reset-requests": "6h12m",
            },
            body={
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {
                    "prompt_tokens": 7,
                    "completion_tokens": 11,
                },
            },
        ),
    )

    result = await _executor(transport).execute_dispatch(_execution_input())

    assert result.capacity_observation is not None
    minute_reset_at = result.capacity_observation["minute_reset_at"]
    daily_reset_at = result.capacity_observation["daily_reset_at"]
    assert isinstance(minute_reset_at, datetime)
    assert isinstance(daily_reset_at, datetime)
    assert minute_reset_at < daily_reset_at


@pytest.mark.asyncio
async def test_auth_error_maps_to_terminal_failed() -> None:
    transport = FakeGroqTransport(
        response=GroqTransportResponse(
            status_code=401,
            headers={},
            body={"error": {"message": "Unauthorized"}},
        ),
    )

    result = await _executor(transport).execute_dispatch(_execution_input())

    assert result.status is LlmDispatchExecutionStatus.TERMINAL_FAILED
    assert result.error_kind == "auth_error"


def test_executor_does_not_import_legacy_provider_port_or_task_use_cases() -> None:
    from pathlib import Path

    source = Path(
        "src/contexts/llm_runtime/infrastructure/providers/groq/"
        "groq_dispatch_executor.py",
    ).read_text(encoding="utf-8")

    forbidden = (
        "LlmProviderPort",
        "ExecuteLlmTask",
        "ExecuteAndRecordLlmTask",
    )
    for marker in forbidden:
        assert marker not in source
