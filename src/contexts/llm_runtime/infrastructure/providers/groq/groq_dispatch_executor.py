from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import cast

import structlog

from src.contexts.llm_runtime.application.ports.llm_dispatch_executor_port import (
    LlmDispatchExecutionInput,
    LlmDispatchExecutionResult,
    LlmDispatchExecutionStatus,
    LlmDispatchExecutorPort,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    LlmModelExecutionSettings,
)
from src.contexts.llm_runtime.domain.entities.model_profile import ModelProfile
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute
from src.contexts.llm_runtime.domain.value_objects.model_id import ModelId
from src.contexts.llm_runtime.domain.value_objects.provider_account_ref import (
    ProviderAccountRef,
)
from src.contexts.llm_runtime.domain.value_objects.provider_id import ProviderId
from src.contexts.llm_runtime.domain.value_objects.token_usage import TokenUsage
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_chat_request_builder import (
    GroqChatMessage,
    GroqChatMessageRole,
    GroqChatRequestBuilder,
    GroqChatRequestOptions,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_provider_response_mapper import (
    GroqProviderHttpResponse,
    GroqProviderMappedResponse,
    GroqProviderResponseMapper,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_transport_port import (
    GroqTransportPort,
)


LOGGER = structlog.get_logger(__name__)


DEFAULT_GROQ_MAX_COMPLETION_TOKEN_GAP = 300
DEFAULT_GROQ_PROVIDER_COMPLETION_TOKENS = 2048


@dataclass(frozen=True, slots=True)
class GroqDispatchExecutor(LlmDispatchExecutorPort):
    transport: GroqTransportPort
    model_profiles: tuple[ModelProfile, ...]
    transports_by_account_ref: Mapping[str, GroqTransportPort] = field(
        default_factory=dict,
    )
    max_completion_token_gap: int = DEFAULT_GROQ_MAX_COMPLETION_TOKEN_GAP
    request_builder: GroqChatRequestBuilder = GroqChatRequestBuilder()
    response_mapper: GroqProviderResponseMapper = GroqProviderResponseMapper()

    def __post_init__(self) -> None:
        if self.max_completion_token_gap < 0:
            raise ValueError("max_completion_token_gap must be >= 0")

    async def execute_dispatch(
        self,
        execution_input: LlmDispatchExecutionInput,
    ) -> LlmDispatchExecutionResult:
        request_started_at = datetime.now(timezone.utc)

        try:
            parsed = _ParsedGroqDispatchPayload.from_execution_input(
                execution_input,
            )
            model_profile = self._find_model_profile(route=parsed.route)
            max_completion_tokens = _resolve_max_completion_tokens(
                parsed=parsed,
                model_profile=model_profile,
                completion_gap_tokens=self.max_completion_token_gap,
            )
            request = self.request_builder.build(
                route=parsed.route,
                model_profile=model_profile,
                messages=parsed.messages,
                options=GroqChatRequestOptions(
                    max_completion_tokens=max_completion_tokens,
                    execution_settings=parsed.execution_settings,
                ),
            )
            message_diagnostics = _message_diagnostics(parsed.messages)
            LOGGER.info(
                "llm_groq_request_started",
                workflow_run_id=parsed.workflow_run_id,
                work_item_id=execution_input.work_item_id,
                dispatch_attempt_id=execution_input.attempt_id,
                attempt_number=execution_input.attempt_number,
                provider=parsed.provider,
                account_ref=parsed.account_ref,
                model_ref=parsed.model_ref,
                request_started_at=request_started_at.isoformat(),
                timeout_seconds=getattr(
                    _transport_for_account(
                        fallback_transport=self.transport,
                        transports_by_account_ref=self.transports_by_account_ref,
                        account_ref=parsed.account_ref,
                    ),
                    "timeout_seconds",
                    None,
                ),
                estimated_input_tokens=parsed.input_tokens,
                planned_output_tokens=parsed.planned_output_tokens,
                required_window_tokens=parsed.required_window_tokens,
                max_completion_tokens=request.payload.get("max_completion_tokens"),
                message_count=len(parsed.messages),
                system_message_char_count=message_diagnostics[
                    "system_message_char_count"
                ],
                user_message_char_count=message_diagnostics["user_message_char_count"],
                total_message_char_count=message_diagnostics[
                    "total_message_char_count"
                ],
                input_tokens=parsed.input_tokens,
                response_format=request.payload.get("response_format"),
                temperature=request.payload.get("temperature"),
                reasoning_enabled=parsed.execution_settings.reasoning_enabled,
                reasoning_effort=request.payload.get("reasoning_effort"),
            )
        except (TypeError, ValueError) as exc:
            LOGGER.warning(
                "knowledge_llm_groq_invalid_dispatch_payload",
                attempt_id=execution_input.attempt_id,
                work_item_id=execution_input.work_item_id,
                attempt_number=execution_input.attempt_number,
                error=str(exc),
            )
            return _terminal_invalid_dispatch_payload(finished_at=request_started_at)

        transport = _transport_for_account(
            fallback_transport=self.transport,
            transports_by_account_ref=self.transports_by_account_ref,
            account_ref=parsed.account_ref,
        )
        LOGGER.info(
            "llm_dispatch_transport_context",
            workflow_run_id=parsed.workflow_run_id,
            dispatch_attempt_id=execution_input.attempt_id,
            work_item_id=execution_input.work_item_id,
            attempt_number=execution_input.attempt_number,
            account_ref=parsed.account_ref,
            model_ref=parsed.model_ref,
            request_started_at=request_started_at.isoformat(),
            estimated_input_tokens=parsed.input_tokens,
            planned_output_tokens=parsed.planned_output_tokens,
            required_window_tokens=parsed.required_window_tokens,
            max_completion_tokens=request.payload.get("max_completion_tokens"),
        )
        LOGGER.info(
            "knowledge_llm_groq_transport_start",
            attempt_id=execution_input.attempt_id,
            work_item_id=execution_input.work_item_id,
            provider=parsed.provider,
            account_ref=parsed.account_ref,
            model_ref=parsed.model_ref,
        )
        try:
            transport_response = transport.post_chat_completions(
                payload=dict(request.payload),
            )
        except Exception:
            LOGGER.exception(
                "knowledge_llm_groq_transport_exception",
                attempt_id=execution_input.attempt_id,
                work_item_id=execution_input.work_item_id,
                provider=parsed.provider,
                account_ref=parsed.account_ref,
                model_ref=parsed.model_ref,
            )
            raise

        response_received_at = datetime.now(timezone.utc)
        duration_ms = int(
            (response_received_at - request_started_at).total_seconds() * 1000
        )
        body_diagnostics = _response_body_diagnostics(transport_response.body)
        rate_limit_headers = _rate_limit_header_diagnostics(transport_response.headers)
        provider_request_id = _provider_request_id(transport_response.headers)
        LOGGER.info(
            "llm_groq_response_received",
            workflow_run_id=parsed.workflow_run_id,
            dispatch_attempt_id=execution_input.attempt_id,
            work_item_id=execution_input.work_item_id,
            attempt_number=execution_input.attempt_number,
            provider=parsed.provider,
            account_ref=parsed.account_ref,
            model_ref=parsed.model_ref,
            status_code=transport_response.status_code,
            duration_ms=duration_ms,
            content_type=_header_value(transport_response.headers, "content-type"),
            provider_request_id=provider_request_id,
            response_body_serialized_char_count=body_diagnostics[
                "serialized_char_count"
            ],
            response_body_top_level_keys=body_diagnostics["top_level_key_count"],
            response_body_type=body_diagnostics["body_type"],
            **rate_limit_headers,
        )
        if transport_response.status_code >= 400:
            error_diagnostics = _provider_error_diagnostics(transport_response.body)
            LOGGER.warning(
                "llm_groq_provider_error",
                workflow_run_id=parsed.workflow_run_id,
                dispatch_attempt_id=execution_input.attempt_id,
                work_item_id=execution_input.work_item_id,
                attempt_number=execution_input.attempt_number,
                provider=parsed.provider,
                account_ref=parsed.account_ref,
                model_ref=parsed.model_ref,
                status_code=transport_response.status_code,
                error_message=error_diagnostics["error_message"],
                error_type=error_diagnostics["error_type"],
                error_code=error_diagnostics["error_code"],
                provider_error_shape=error_diagnostics["error_shape"],
                provider_request_id=provider_request_id,
                provider_error_extra_keys=error_diagnostics["extra_keys"],
            )
        else:
            error_diagnostics = None
        observed_at = response_received_at
        mapped = self.response_mapper.map_response(
            response=GroqProviderHttpResponse(
                status_code=transport_response.status_code,
                headers=transport_response.headers,
                body=transport_response.body,
            ),
            observed_at=observed_at,
        )

        provider_result = mapped.provider_result
        classification = _classification_diagnostics(
            body=transport_response.body,
            status_code=transport_response.status_code,
            provider_result=provider_result,
            mapped=mapped,
            error_diagnostics=error_diagnostics,
        )
        LOGGER.info(
            "llm_groq_response_classified",
            workflow_run_id=parsed.workflow_run_id,
            dispatch_attempt_id=execution_input.attempt_id,
            work_item_id=execution_input.work_item_id,
            attempt_number=execution_input.attempt_number,
            provider=parsed.provider,
            account_ref=parsed.account_ref,
            model_ref=parsed.model_ref,
            status_code=transport_response.status_code,
            mapped_status=classification["mapped_status"],
            mapped_error_kind=classification["mapped_error_kind"],
            matched_rule=classification["matched_rule"],
            has_provider_error=classification["has_provider_error"],
            has_structured_provider_error_message=classification[
                "has_structured_provider_error_message"
            ],
            provider_error_shape=classification["provider_error_shape"],
            has_usage=classification["has_usage"],
            has_rate_limit_headers=any(
                value is not None for value in rate_limit_headers.values()
            ),
            next_attempt_at=classification["next_attempt_at"],
            quota_remaining_minute_requests=mapped.quota_snapshot.remaining_requests_minute,
            quota_remaining_minute_tokens=mapped.quota_snapshot.remaining_tokens_minute,
            quota_remaining_daily_requests=mapped.quota_snapshot.remaining_requests_day,
            quota_remaining_daily_tokens=mapped.quota_snapshot.remaining_tokens_day,
            quota_minute_reset_at=mapped.quota_snapshot.minute_reset_at.isoformat()
            if mapped.quota_snapshot.minute_reset_at is not None
            else None,
            quota_daily_reset_at=mapped.quota_snapshot.daily_reset_at.isoformat()
            if mapped.quota_snapshot.daily_reset_at is not None
            else None,
            quota_unavailable_until=mapped.quota_snapshot.unavailable_until.isoformat()
            if mapped.quota_snapshot.unavailable_until is not None
            else None,
        )
        raw_text = getattr(provider_result, "raw_text", None)
        if isinstance(raw_text, str):
            output_payload: dict[str, object] = {
                "raw_text": raw_text,
                "provider": parsed.provider,
                "model_ref": parsed.model_ref,
                "account_ref": parsed.account_ref,
            }
            usage = getattr(provider_result, "usage", None)
            token_usage = usage if isinstance(usage, TokenUsage) else None
            if token_usage is not None:
                output_payload["usage"] = {
                    "input_tokens": token_usage.input_tokens,
                    "output_tokens": token_usage.output_tokens,
                    "total_tokens": token_usage.total_tokens,
                }
            LOGGER.info(
                "knowledge_llm_groq_execution_succeeded",
                attempt_id=execution_input.attempt_id,
                work_item_id=execution_input.work_item_id,
                provider=parsed.provider,
                account_ref=parsed.account_ref,
                model_ref=parsed.model_ref,
                raw_text_char_count=len(raw_text),
                input_tokens=token_usage.input_tokens
                if token_usage is not None
                else None,
                output_tokens=token_usage.output_tokens
                if token_usage is not None
                else None,
                total_tokens=token_usage.total_tokens
                if token_usage is not None
                else None,
            )
            return LlmDispatchExecutionResult(
                status=LlmDispatchExecutionStatus.SUCCEEDED,
                finished_at=observed_at,
                output_payload=output_payload,
                capacity_observation=_capacity_observation_payload(
                    parsed=parsed,
                    mapped=mapped,
                    observed_at=observed_at,
                    status=LlmDispatchExecutionStatus.SUCCEEDED,
                    usage=token_usage,
                ),
            )

        error_kind = getattr(provider_result, "error_kind", None)
        if not isinstance(error_kind, LlmErrorKind):
            error_kind = LlmErrorKind.UNKNOWN

        wait_until = getattr(provider_result, "wait_until", None)
        status = _map_error_kind_to_status(
            error_kind=error_kind,
            wait_until=wait_until,
        )
        next_attempt_at = wait_until if isinstance(wait_until, datetime) else None

        LOGGER.warning(
            "knowledge_llm_groq_execution_failed",
            attempt_id=execution_input.attempt_id,
            work_item_id=execution_input.work_item_id,
            provider=parsed.provider,
            account_ref=parsed.account_ref,
            model_ref=parsed.model_ref,
            error_kind=error_kind.value,
            mapped_status=status.value,
            next_attempt_at=next_attempt_at.isoformat()
            if next_attempt_at is not None
            else None,
        )
        return LlmDispatchExecutionResult(
            status=status,
            finished_at=observed_at,
            error_kind=error_kind.value,
            next_attempt_at=next_attempt_at,
            capacity_observation=_capacity_observation_payload(
                parsed=parsed,
                mapped=mapped,
                observed_at=observed_at,
                status=status,
                usage=None,
            ),
        )

    def _find_model_profile(self, *, route: LlmRoute) -> ModelProfile:
        for profile in self.model_profiles:
            if (
                profile.provider_id == route.provider_id
                and profile.model_id == route.model_id
            ):
                return profile
        raise ValueError("No ModelProfile found for route")


def _transport_for_account(
    *,
    fallback_transport: GroqTransportPort,
    transports_by_account_ref: Mapping[str, GroqTransportPort],
    account_ref: str,
) -> GroqTransportPort:
    _require_non_empty_text(account_ref, field_name="account_ref")
    transport = transports_by_account_ref.get(account_ref)
    if transport is None:
        return fallback_transport
    return transport


@dataclass(frozen=True, slots=True)
class _ParsedGroqDispatchPayload:
    workflow_run_id: str | None
    provider: str
    account_ref: str
    model_ref: str
    route: LlmRoute
    messages: tuple[GroqChatMessage, ...]
    execution_settings: LlmModelExecutionSettings
    input_tokens: int
    planned_output_tokens: int
    safety_gap_tokens: int
    model_tpm_limit: int
    provider_default_completion_tokens: int
    required_window_tokens: int
    max_completion_tokens: int | None

    @classmethod
    def from_execution_input(
        cls,
        execution_input: LlmDispatchExecutionInput,
    ) -> "_ParsedGroqDispatchPayload":
        allocation = _require_mapping(
            execution_input.dispatch_payload,
            "llm_allocation",
        )
        schedule_payload = _require_mapping(
            execution_input.dispatch_payload,
            "schedule_payload",
        )
        execution_settings_payload = _require_mapping(
            execution_input.dispatch_payload,
            "llm_execution_settings",
        )

        provider = _require_text(allocation, "provider")
        account_ref = _require_text(allocation, "account_ref")
        model_ref = _require_text(allocation, "model_ref")
        slot_index = allocation.get("slot_index")
        if not isinstance(slot_index, int):
            raise ValueError("llm_allocation.slot_index must be int")

        route = LlmRoute(
            provider_id=ProviderId(provider),
            model_id=ModelId(model_ref),
            account_ref=ProviderAccountRef(account_ref),
        )

        estimate_payload = _require_mapping(
            schedule_payload,
            "llm_capacity_estimate",
        )
        input_tokens = _parse_input_tokens(estimate_payload)
        planned_output_tokens = _parse_planned_output_tokens(estimate_payload)
        safety_gap_tokens = _parse_safety_gap_tokens(estimate_payload)
        model_tpm_limit = _parse_model_tpm_limit(estimate_payload)
        provider_default_completion_tokens = _parse_provider_default_completion_tokens(
            estimate_payload,
        )
        required_window_tokens = _parse_required_window_tokens(estimate_payload)
        if required_window_tokens < input_tokens + planned_output_tokens:
            raise ValueError(
                "llm_capacity_estimate.required_window_tokens must be >= "
                "input_tokens + planned_output_tokens"
            )

        return cls(
            workflow_run_id=_optional_text(schedule_payload, "workflow_run_id"),
            provider=provider,
            account_ref=account_ref,
            model_ref=model_ref,
            route=route,
            messages=_parse_provider_messages(schedule_payload),
            execution_settings=_parse_execution_settings(
                execution_settings_payload,
            ),
            input_tokens=input_tokens,
            planned_output_tokens=planned_output_tokens,
            safety_gap_tokens=safety_gap_tokens,
            model_tpm_limit=model_tpm_limit,
            provider_default_completion_tokens=provider_default_completion_tokens,
            required_window_tokens=required_window_tokens,
            max_completion_tokens=_parse_optional_positive_int(
                estimate_payload,
                "max_completion_tokens",
            ),
        )


def _resolve_max_completion_tokens(
    *,
    parsed: _ParsedGroqDispatchPayload,
    model_profile: ModelProfile,
    completion_gap_tokens: int,
) -> int | None:
    if parsed.max_completion_tokens is not None:
        return min(parsed.max_completion_tokens, model_profile.max_output_tokens)

    safety_gap_tokens = max(parsed.safety_gap_tokens, completion_gap_tokens)
    remaining_after_input_tokens = (
        parsed.model_tpm_limit - parsed.input_tokens - safety_gap_tokens
    )
    if remaining_after_input_tokens <= parsed.provider_default_completion_tokens:
        return None
    return min(remaining_after_input_tokens, model_profile.max_output_tokens)


def _parse_input_tokens(estimate_payload: Mapping[str, object]) -> int:
    value = estimate_payload.get("input_tokens")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("llm_capacity_estimate.input_tokens must be int")
    if value <= 0:
        raise ValueError("llm_capacity_estimate.input_tokens must be > 0")
    return value


def _parse_planned_output_tokens(estimate_payload: Mapping[str, object]) -> int:
    value = estimate_payload.get("planned_output_tokens")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("llm_capacity_estimate.planned_output_tokens must be int")
    if value < 0:
        raise ValueError("llm_capacity_estimate.planned_output_tokens must be >= 0")
    return value


def _parse_safety_gap_tokens(estimate_payload: Mapping[str, object]) -> int:
    value = estimate_payload.get("safety_gap_tokens")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("llm_capacity_estimate.safety_gap_tokens must be int")
    if value < 0:
        raise ValueError("llm_capacity_estimate.safety_gap_tokens must be >= 0")
    return value


def _parse_model_tpm_limit(estimate_payload: Mapping[str, object]) -> int:
    value = estimate_payload.get("model_tpm_limit")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("llm_capacity_estimate.model_tpm_limit must be int")
    if value <= 0:
        raise ValueError("llm_capacity_estimate.model_tpm_limit must be > 0")
    return value


def _parse_provider_default_completion_tokens(
    estimate_payload: Mapping[str, object],
) -> int:
    value = estimate_payload.get("provider_default_completion_tokens")
    if value is None:
        return DEFAULT_GROQ_PROVIDER_COMPLETION_TOKENS
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(
            "llm_capacity_estimate.provider_default_completion_tokens must be int"
        )
    if value <= 0:
        raise ValueError(
            "llm_capacity_estimate.provider_default_completion_tokens must be > 0"
        )
    return value


def _parse_required_window_tokens(estimate_payload: Mapping[str, object]) -> int:
    value = estimate_payload.get("required_window_tokens")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("llm_capacity_estimate.required_window_tokens must be int")
    if value <= 0:
        raise ValueError("llm_capacity_estimate.required_window_tokens must be > 0")
    return value


def _parse_optional_positive_int(
    payload: Mapping[str, object],
    key: str,
) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"llm_capacity_estimate.{key} must be int")
    if value <= 0:
        raise ValueError(f"llm_capacity_estimate.{key} must be > 0")
    return value


def _parse_provider_messages(
    schedule_payload: Mapping[str, object],
) -> tuple[GroqChatMessage, ...]:
    raw_messages = schedule_payload.get("provider_messages")
    if not isinstance(raw_messages, (list, tuple)):
        raise ValueError("schedule_payload.provider_messages is required")
    if not raw_messages:
        raise ValueError("schedule_payload.provider_messages must be non-empty")

    messages: list[GroqChatMessage] = []
    for raw_message in raw_messages:
        if not isinstance(raw_message, Mapping):
            raise ValueError("provider_messages entries must be mappings")
        message = cast(Mapping[str, object], raw_message)
        role = _require_text(message, "role")
        content = _require_text(message, "content")
        try:
            groq_role = GroqChatMessageRole(role)
        except ValueError as exc:
            raise ValueError("Unsupported provider message role") from exc
        messages.append(
            GroqChatMessage(
                role=groq_role,
                content=content,
            ),
        )

    return tuple(messages)


def _optional_text(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if isinstance(value, str) and value.strip():
        return value
    return None


def _parse_execution_settings(
    payload: Mapping[str, object],
) -> LlmModelExecutionSettings:
    reasoning_enabled = payload.get("reasoning_enabled")
    if not isinstance(reasoning_enabled, bool):
        raise ValueError("llm_execution_settings.reasoning_enabled must be bool")

    reasoning_effort = payload.get("reasoning_effort")
    if reasoning_effort is not None and not isinstance(reasoning_effort, str):
        raise ValueError("llm_execution_settings.reasoning_effort must be str")

    return LlmModelExecutionSettings(
        reasoning_enabled=reasoning_enabled,
        reasoning_effort=reasoning_effort,
    )


def _map_error_kind_to_status(
    *,
    error_kind: LlmErrorKind,
    wait_until: object,
) -> LlmDispatchExecutionStatus:
    if error_kind is LlmErrorKind.MINUTE_LIMIT and isinstance(wait_until, datetime):
        return LlmDispatchExecutionStatus.RETRYABLE_FAILED
    if error_kind is LlmErrorKind.AUTH_ERROR:
        return LlmDispatchExecutionStatus.TERMINAL_FAILED
    return LlmDispatchExecutionStatus.RETRYABLE_FAILED


def _capacity_observation_payload(
    *,
    parsed: _ParsedGroqDispatchPayload,
    mapped: GroqProviderMappedResponse,
    observed_at: datetime,
    status: LlmDispatchExecutionStatus,
    usage: TokenUsage | None,
) -> dict[str, object]:
    quota = mapped.quota_snapshot
    return {
        "provider": parsed.provider,
        "account_ref": parsed.account_ref,
        "model_ref": parsed.model_ref,
        "remaining_minute_requests": quota.remaining_requests_minute,
        "remaining_minute_tokens": quota.remaining_tokens_minute,
        "remaining_daily_requests": quota.remaining_requests_day,
        "remaining_daily_tokens": quota.remaining_tokens_day,
        "minute_reset_at": quota.minute_reset_at,
        "daily_reset_at": quota.daily_reset_at,
        "actual_prompt_tokens": usage.input_tokens if usage is not None else None,
        "actual_completion_tokens": usage.output_tokens if usage is not None else None,
        "actual_total_tokens": usage.total_tokens if usage is not None else None,
        "outcome_class": status.value,
        "observed_at": observed_at,
    }


def _terminal_invalid_dispatch_payload(
    *,
    finished_at: datetime,
) -> LlmDispatchExecutionResult:
    return LlmDispatchExecutionResult(
        status=LlmDispatchExecutionStatus.TERMINAL_FAILED,
        finished_at=finished_at,
        error_kind="invalid_dispatch_payload",
    )


def _require_mapping(
    payload: Mapping[str, object],
    key: str,
) -> Mapping[str, object]:
    value = payload.get(key)
    if not isinstance(value, Mapping):
        raise ValueError(f"{key} must be Mapping")
    return cast(Mapping[str, object], value)


def _require_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be str")
    _require_non_empty_text(value, field_name=key)
    return value


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _message_diagnostics(
    messages: tuple[GroqChatMessage, ...],
) -> dict[str, int]:
    system_chars = 0
    user_chars = 0
    total_chars = 0
    for message in messages:
        content_chars = len(message.content)
        total_chars += content_chars
        if message.role is GroqChatMessageRole.SYSTEM:
            system_chars += content_chars
        elif message.role is GroqChatMessageRole.USER:
            user_chars += content_chars
    return {
        "system_message_char_count": system_chars,
        "user_message_char_count": user_chars,
        "total_message_char_count": total_chars,
    }


def _response_body_diagnostics(body: object) -> dict[str, object]:
    try:
        serialized = json.dumps(
            body,
            ensure_ascii=False,
            sort_keys=True,
            default=str,
        )
    except TypeError:
        serialized = str(body)
    top_level_key_count = len(body) if isinstance(body, Mapping) else None
    return {
        "serialized_char_count": len(serialized),
        "top_level_key_count": top_level_key_count,
        "body_type": type(body).__name__,
    }


def _provider_error_diagnostics(body: Mapping[str, object]) -> dict[str, object]:
    error = body.get("error")
    if isinstance(error, Mapping):
        known_keys = {"message", "type", "code"}
        return {
            "error_message": _optional_string_value(error.get("message")),
            "error_type": _optional_string_value(error.get("type")),
            "error_code": _optional_string_value(error.get("code")),
            "error_shape": "nested_error_object",
            "extra_keys": tuple(
                sorted(str(key) for key in error.keys() if key not in known_keys)
            ),
        }
    if isinstance(error, str):
        return {
            "error_message": None,
            "error_type": None,
            "error_code": None,
            "error_shape": "error_string_omitted",
            "extra_keys": ("error",),
        }
    return {
        "error_message": None,
        "error_type": None,
        "error_code": None,
        "error_shape": "unknown_mapping",
        "extra_keys": tuple(sorted(str(key) for key in body.keys())),
    }


def _optional_string_value(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value[:500]
    return str(value)[:500]


def _rate_limit_header_diagnostics(
    headers: Mapping[str, object],
) -> dict[str, object]:
    return {
        "limit_requests": _header_value(headers, "x-ratelimit-limit-requests"),
        "remaining_requests": _header_value(
            headers,
            "x-ratelimit-remaining-requests",
        ),
        "reset_requests": _header_value(headers, "x-ratelimit-reset-requests"),
        "limit_tokens": _header_value(headers, "x-ratelimit-limit-tokens"),
        "remaining_tokens": _header_value(headers, "x-ratelimit-remaining-tokens"),
        "reset_tokens": _header_value(headers, "x-ratelimit-reset-tokens"),
        "retry_after": _header_value(headers, "retry-after"),
    }


def _provider_request_id(headers: Mapping[str, object]) -> str | None:
    for key in ("x-request-id", "x-groq-request-id", "request-id"):
        value = _header_value(headers, key)
        if value:
            return value
    return None


def _header_value(headers: Mapping[str, object], name: str) -> str | None:
    normalized_name = name.lower()
    for key, value in headers.items():
        if str(key).lower() == normalized_name:
            return str(value) if value is not None else None
    return None


def _classification_diagnostics(
    *,
    body: Mapping[str, object],
    status_code: int,
    provider_result: object,
    mapped: GroqProviderMappedResponse,
    error_diagnostics: Mapping[str, object] | None,
) -> dict[str, object]:
    error_kind = getattr(provider_result, "error_kind", None)
    mapped_error_kind = (
        error_kind.value if isinstance(error_kind, LlmErrorKind) else None
    )
    wait_until = getattr(provider_result, "wait_until", None)
    mapped_status = (
        _map_error_kind_to_status(
            error_kind=error_kind,
            wait_until=wait_until,
        ).value
        if isinstance(error_kind, LlmErrorKind)
        else LlmDispatchExecutionStatus.SUCCEEDED.value
    )
    return {
        "mapped_status": mapped_status,
        "mapped_error_kind": mapped_error_kind,
        "matched_rule": mapped.matched_rule,
        "has_provider_error": status_code >= 400,
        "has_structured_provider_error_message": (
            error_diagnostics is not None
            and error_diagnostics.get("error_message") is not None
        ),
        "provider_error_shape": error_diagnostics.get("error_shape")
        if error_diagnostics is not None
        else None,
        "has_usage": isinstance(body.get("usage"), Mapping),
        "next_attempt_at": wait_until.isoformat()
        if isinstance(wait_until, datetime)
        else None,
    }
