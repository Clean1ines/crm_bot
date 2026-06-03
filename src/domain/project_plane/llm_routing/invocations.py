from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from .limits import LlmTokenUsage
from .routes import LlmRouteAttempt
from .shared import (
    JsonValue,
    OperationName,
    require_non_empty,
)


class LlmInvocationStatus(StrEnum):
    SUCCESS = "success"
    RATE_LIMITED = "rate_limited"
    DAILY_LIMITED = "daily_limited"
    REQUEST_TOO_LARGE = "request_too_large"
    OUTPUT_TOO_LARGE = "output_too_large"
    PROVIDER_ERROR = "provider_error"
    NETWORK_ERROR = "network_error"
    CANCELLED = "cancelled"
    INVALID_JSON = "invalid_json"


@dataclass(frozen=True, slots=True)
class LlmJsonInvocationRequest:
    operation_name: OperationName
    prompt: str
    route_purpose: str
    idempotency_key: str | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.operation_name, field_name="operation_name")
        require_non_empty(self.prompt, field_name="prompt")
        require_non_empty(self.route_purpose, field_name="route_purpose")
        if self.idempotency_key is not None:
            require_non_empty(self.idempotency_key, field_name="idempotency_key")


@dataclass(frozen=True, slots=True)
class LlmInvocationFailure:
    status: LlmInvocationStatus
    error_kind: str
    user_message: str
    internal_message: str
    cooldown_seconds: int | None = None

    def __post_init__(self) -> None:
        if self.status is LlmInvocationStatus.SUCCESS:
            raise ValueError("failure status must not be success")
        require_non_empty(self.error_kind, field_name="error_kind")
        require_non_empty(self.user_message, field_name="user_message")
        require_non_empty(self.internal_message, field_name="internal_message")
        if self.cooldown_seconds is not None and self.cooldown_seconds < 0:
            raise ValueError("cooldown_seconds must be non-negative")


@dataclass(frozen=True, slots=True)
class LlmJsonInvocationResult:
    status: LlmInvocationStatus
    parsed_json: JsonValue | None
    raw_text: str
    token_usage: LlmTokenUsage
    attempts: tuple[LlmRouteAttempt, ...]
    failure: LlmInvocationFailure | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.attempts:
            raise ValueError("invocation result requires at least one attempt")
        if self.status is LlmInvocationStatus.SUCCESS:
            if self.failure is not None:
                raise ValueError("successful invocation cannot have failure")
            if self.parsed_json is None:
                raise ValueError("successful JSON invocation requires parsed_json")
        if self.status is not LlmInvocationStatus.SUCCESS and self.failure is None:
            raise ValueError("failed invocation requires failure")
