from __future__ import annotations

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
            LOGGER.info(
                "knowledge_llm_groq_request_prepared",
                attempt_id=execution_input.attempt_id,
                work_item_id=execution_input.work_item_id,
                attempt_number=execution_input.attempt_number,
                provider=parsed.provider,
                account_ref=parsed.account_ref,
                model_ref=parsed.model_ref,
                message_count=len(parsed.messages),
                message_char_count=sum(
                    len(message.content) for message in parsed.messages
                ),
                payload_keys=sorted(request.payload.keys()),
                has_max_completion_tokens="max_completion_tokens" in request.payload,
                max_completion_tokens=request.payload.get("max_completion_tokens"),
                estimated_input_tokens=parsed.estimated_input_tokens,
                reserved_output_tokens=parsed.reserved_output_tokens,
                request_output_cap_tokens=parsed.request_output_cap_tokens,
                response_format=request.payload.get("response_format"),
                temperature=request.payload.get("temperature"),
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

        LOGGER.info(
            "knowledge_llm_groq_transport_response",
            attempt_id=execution_input.attempt_id,
            work_item_id=execution_input.work_item_id,
            provider=parsed.provider,
            account_ref=parsed.account_ref,
            model_ref=parsed.model_ref,
            status_code=transport_response.status_code,
            response_header_keys=sorted(transport_response.headers.keys()),
            response_body_char_count=len(transport_response.body),
        )
        observed_at = datetime.now(timezone.utc)
        mapped = self.response_mapper.map_response(
            response=GroqProviderHttpResponse(
                status_code=transport_response.status_code,
                headers=transport_response.headers,
                body=transport_response.body,
            ),
            observed_at=observed_at,
        )

        provider_result = mapped.provider_result
        LOGGER.info(
            "knowledge_llm_groq_mapped_response",
            attempt_id=execution_input.attempt_id,
            work_item_id=execution_input.work_item_id,
            provider=parsed.provider,
            account_ref=parsed.account_ref,
            model_ref=parsed.model_ref,
            provider_result_type=type(provider_result).__name__,
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
        LOGGER.warning(
            "knowledge_llm_groq_execution_failed",
            attempt_id=execution_input.attempt_id,
            work_item_id=execution_input.work_item_id,
            provider=parsed.provider,
            account_ref=parsed.account_ref,
            model_ref=parsed.model_ref,
            error_kind=error_kind.value,
            mapped_status=status.value,
            provider_wait_until=wait_until.isoformat()
            if isinstance(wait_until, datetime)
            else None,
        )
        return LlmDispatchExecutionResult(
            status=status,
            finished_at=observed_at,
            error_kind=error_kind.value,
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
    provider: str
    account_ref: str
    model_ref: str
    route: LlmRoute
    messages: tuple[GroqChatMessage, ...]
    execution_settings: LlmModelExecutionSettings
    estimated_input_tokens: int
    reserved_output_tokens: int
    request_output_cap_tokens: int | None

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

        return cls(
            provider=provider,
            account_ref=account_ref,
            model_ref=model_ref,
            route=route,
            messages=_parse_provider_messages(schedule_payload),
            execution_settings=_parse_execution_settings(
                execution_settings_payload,
            ),
            estimated_input_tokens=_parse_estimated_input_tokens(schedule_payload),
            reserved_output_tokens=_parse_reserved_output_tokens(schedule_payload),
            request_output_cap_tokens=_parse_request_output_cap_tokens(
                schedule_payload,
            ),
        )


def _resolve_max_completion_tokens(
    *,
    parsed: _ParsedGroqDispatchPayload,
    model_profile: ModelProfile,
    completion_gap_tokens: int,
) -> int | None:
    if parsed.request_output_cap_tokens is not None:
        if parsed.request_output_cap_tokens > model_profile.max_output_tokens:
            raise ValueError(
                "llm_capacity_estimate.request_output_cap_tokens must not exceed "
                "model max_output_tokens"
            )
        return parsed.request_output_cap_tokens

    requested_output_tokens = parsed.reserved_output_tokens - completion_gap_tokens
    requested_output_tokens = min(
        requested_output_tokens,
        model_profile.max_output_tokens,
    )
    if requested_output_tokens <= 0:
        return None
    return requested_output_tokens


def _parse_estimated_input_tokens(schedule_payload: Mapping[str, object]) -> int:
    estimate_payload = _require_mapping(schedule_payload, "llm_capacity_estimate")
    value = estimate_payload.get("estimated_input_tokens")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("llm_capacity_estimate.estimated_input_tokens must be int")
    if value <= 0:
        raise ValueError("llm_capacity_estimate.estimated_input_tokens must be > 0")
    return value


def _parse_reserved_output_tokens(schedule_payload: Mapping[str, object]) -> int:
    estimate_payload = _require_mapping(schedule_payload, "llm_capacity_estimate")
    value = estimate_payload.get("reserved_output_tokens")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("llm_capacity_estimate.reserved_output_tokens must be int")
    if value < 0:
        raise ValueError("llm_capacity_estimate.reserved_output_tokens must be >= 0")
    return value


def _parse_request_output_cap_tokens(
    schedule_payload: Mapping[str, object],
) -> int | None:
    estimate_payload = _require_mapping(schedule_payload, "llm_capacity_estimate")
    value = estimate_payload.get("request_output_cap_tokens")
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("llm_capacity_estimate.request_output_cap_tokens must be int")
    if value <= 0:
        raise ValueError("llm_capacity_estimate.request_output_cap_tokens must be > 0")
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
