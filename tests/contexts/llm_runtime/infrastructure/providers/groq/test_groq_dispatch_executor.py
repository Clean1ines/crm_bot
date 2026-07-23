from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from structlog.testing import capture_logs

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
                "budget_contract_version": "v3",
                "estimator": "test_budget",
                "provider": "groq",
                "model_ref": "qwen/qwen3.6-27b",
                "model_tpm_limit": 8000,
                "model_char_to_token_multiplier": "2.8",
                "phase": "test",
                "operation": "dispatch",
                "prompt_tokens": 500,
                "artifact_tokens": 500,
                "input_tokens": 1000,
                "planned_output_tokens": 1000,
                "safety_gap_tokens": 300,
                "required_window_tokens": 2300,
            },
        },
        "llm_allocation": {
            "provider": "groq",
            "account_ref": "groq_org_primary",
            "model_ref": "qwen/qwen3.6-27b",
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


def _event(logs: list[dict[str, object]], name: str) -> dict[str, object]:
    for event in logs:
        if event.get("event") == name:
            return event
    raise AssertionError(f"log event not found: {name}")


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
        "model_ref": "qwen/qwen3.6-27b",
        "account_ref": "groq_org_primary",
        "usage": {
            "input_tokens": 7,
            "output_tokens": 11,
            "total_tokens": 18,
        },
    }
    assert len(transport.payloads) == 1
    request_payload = transport.payloads[0]
    assert request_payload["model"] == "qwen/qwen3.6-27b"
    assert request_payload["messages"] == [
        {
            "role": "user",
            "content": "Extract claims",
        },
    ]
    assert "reasoning_effort" not in request_payload
    assert request_payload["max_completion_tokens"] == 6700


@pytest.mark.asyncio
async def test_claim_builder_budget_caps_completion_tokens_by_remaining_tpm() -> None:
    transport = FakeGroqTransport(response=_success_response(raw_text='{"done": true}'))
    schedule_payload = {
        "provider_messages": [
            {
                "role": "user",
                "content": "Extract claims",
            },
        ],
        "llm_capacity_estimate": {
            "budget_contract_version": "v3",
            "estimator": "measured_prompt_3008_source_char_div_2.8",
            "provider": "groq",
            "model_ref": "qwen/qwen3.6-27b",
            "model_tpm_limit": 8000,
            "model_char_to_token_multiplier": "2.8",
            "phase": "claim_builder_section_extraction",
            "operation": "section_extraction",
            "prompt_tokens": 3008,
            "artifact_tokens": 369,
            "input_tokens": 3377,
            "planned_output_tokens": 369,
            "safety_gap_tokens": 100,
            "required_window_tokens": 3846,
        },
    }

    result = await _executor(transport).execute_dispatch(
        _execution_input(
            dispatch_payload=_dispatch_payload(schedule_payload=schedule_payload)
        ),
    )

    assert result.status is LlmDispatchExecutionStatus.SUCCEEDED
    request_payload = transport.payloads[0]
    assert request_payload["max_completion_tokens"] == 4323
    assert 3357 + request_payload["max_completion_tokens"] <= 8000


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
async def test_invalid_dispatch_missing_required_window_tokens_returns_terminal_failed() -> (
    None
):
    transport = FakeGroqTransport(response=_success_response())
    schedule_payload = {
        "provider_messages": [{"role": "user", "content": "Extract claims"}],
        "llm_capacity_estimate": {
            "budget_contract_version": "v3",
            "input_tokens": 1000,
            "planned_output_tokens": 1000,
            "safety_gap_tokens": 300,
            "model_tpm_limit": 6000,
        },
    }

    result = await _executor(transport).execute_dispatch(
        _execution_input(
            dispatch_payload=_dispatch_payload(schedule_payload=schedule_payload)
        ),
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
    assert result.next_attempt_at is not None
    assert result.next_attempt_at > result.finished_at
    assert result.next_attempt_at <= result.finished_at + timedelta(seconds=2)


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


@pytest.mark.asyncio
async def test_provider_error_logging_serializes_body_and_extracts_error_fields() -> (
    None
):
    transport = FakeGroqTransport(
        response=GroqTransportResponse(
            status_code=400,
            headers={
                "x-request-id": "req-123",
                "x-ratelimit-remaining-tokens": "1234",
            },
            body={
                "error": {
                    "message": "model is not available for this organization",
                    "type": "invalid_request_error",
                    "code": "model_not_available",
                    "api_key": "gsk_this_must_not_be_logged_1234567890",
                    "messages": ["prompt text must not be logged"],
                }
            },
        ),
    )

    with capture_logs() as logs:
        result = await _executor(transport).execute_dispatch(_execution_input())

    assert result.status is LlmDispatchExecutionStatus.RETRYABLE_FAILED
    response_event = _event(logs, "llm_groq_response_received")
    assert response_event["response_body_top_level_keys"] == 1
    assert response_event["response_body_serialized_char_count"] > 1
    assert response_event["response_body_type"] == "dict"
    assert response_event["provider_request_id"] == "req-123"
    assert response_event["remaining_tokens"] == "1234"

    error_event = _event(logs, "llm_groq_provider_error")
    assert (
        error_event["error_message"] == "model is not available for this organization"
    )
    assert error_event["error_type"] == "invalid_request_error"
    assert error_event["error_code"] == "model_not_available"
    assert error_event["provider_error_shape"] == "nested_error_object"
    assert error_event["provider_error_extra_keys"] == ("api_key", "messages")
    assert "provider_error_body_hash" not in error_event
    assert "bounded_raw_body" not in error_event
    serialized_logs = str(logs)
    assert "gsk_" not in serialized_logs
    assert "prompt text must not be logged" not in serialized_logs

    classified_event = _event(logs, "llm_groq_response_classified")
    assert classified_event["matched_rule"] == "unknown_http_400_fallback"
    assert classified_event["mapped_error_kind"] == "invalid_output"
    assert classified_event["has_provider_error"] is True
    assert classified_event["has_structured_provider_error_message"] is True
    assert classified_event["provider_error_shape"] == "nested_error_object"


@pytest.mark.asyncio
async def test_unknown_mapping_provider_error_logging_omits_body_content() -> None:
    transport = FakeGroqTransport(
        response=GroqTransportResponse(
            status_code=500,
            headers={},
            body={"raw_body": "upstream html error"},
        ),
    )

    with capture_logs() as logs:
        result = await _executor(transport).execute_dispatch(_execution_input())

    assert result.status is LlmDispatchExecutionStatus.RETRYABLE_FAILED
    response_event = _event(logs, "llm_groq_response_received")
    assert response_event["response_body_serialized_char_count"] > 1
    error_event = _event(logs, "llm_groq_provider_error")
    assert error_event["error_message"] is None
    assert error_event["provider_error_shape"] == "unknown_mapping"
    assert error_event["provider_error_extra_keys"] == ("raw_body",)
    assert "bounded_raw_body" not in error_event
    classified_event = _event(logs, "llm_groq_response_classified")
    assert classified_event["has_provider_error"] is True
    assert classified_event["has_structured_provider_error_message"] is False
    assert classified_event["provider_error_shape"] == "unknown_mapping"


@pytest.mark.asyncio
async def test_success_logging_does_not_include_generated_text() -> None:
    generated_text = '{"claims": ["very sensitive generated claim"]}'
    transport = FakeGroqTransport(response=_success_response(raw_text=generated_text))

    with capture_logs() as logs:
        result = await _executor(transport).execute_dispatch(_execution_input())

    assert result.status is LlmDispatchExecutionStatus.SUCCEEDED
    serialized_logs = str(logs)
    assert generated_text not in serialized_logs
    success_event = _event(logs, "knowledge_llm_groq_execution_succeeded")
    assert success_event["raw_text_char_count"] == len(generated_text)


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
