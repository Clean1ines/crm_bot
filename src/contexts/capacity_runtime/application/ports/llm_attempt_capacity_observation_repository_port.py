from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True, slots=True)
class LlmAttemptCapacityObservation:
    provider: str
    account_ref: str
    model_ref: str
    remaining_minute_requests: int | None
    remaining_minute_tokens: int | None
    remaining_daily_requests: int | None
    remaining_daily_tokens: int | None
    minute_reset_at: datetime | None
    daily_reset_at: datetime | None
    actual_prompt_tokens: int | None
    actual_completion_tokens: int | None
    actual_total_tokens: int | None
    outcome_class: str
    observed_at: datetime

    def __post_init__(self) -> None:
        _require_non_empty_text(self.provider, "provider")
        _require_non_empty_text(self.account_ref, "account_ref")
        _require_non_empty_text(self.model_ref, "model_ref")
        _require_non_empty_text(self.outcome_class, "outcome_class")
        _require_timezone_aware(self.observed_at, "observed_at")

        for field_name, int_value in (
            ("remaining_minute_requests", self.remaining_minute_requests),
            ("remaining_minute_tokens", self.remaining_minute_tokens),
            ("remaining_daily_requests", self.remaining_daily_requests),
            ("remaining_daily_tokens", self.remaining_daily_tokens),
            ("actual_prompt_tokens", self.actual_prompt_tokens),
            ("actual_completion_tokens", self.actual_completion_tokens),
            ("actual_total_tokens", self.actual_total_tokens),
        ):
            if int_value is not None:
                _require_non_negative_int(int_value, field_name)

        for field_name, datetime_value in (
            ("minute_reset_at", self.minute_reset_at),
            ("daily_reset_at", self.daily_reset_at),
        ):
            if datetime_value is not None:
                _require_timezone_aware(datetime_value, field_name)

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, object],
    ) -> "LlmAttemptCapacityObservation":
        return cls(
            provider=_payload_text(payload, "provider"),
            account_ref=_payload_text(payload, "account_ref"),
            model_ref=_payload_text(payload, "model_ref"),
            remaining_minute_requests=_payload_optional_int(
                payload,
                "remaining_minute_requests",
            ),
            remaining_minute_tokens=_payload_optional_int(
                payload,
                "remaining_minute_tokens",
            ),
            remaining_daily_requests=_payload_optional_int(
                payload,
                "remaining_daily_requests",
            ),
            remaining_daily_tokens=_payload_optional_int(
                payload,
                "remaining_daily_tokens",
            ),
            minute_reset_at=_payload_optional_datetime(payload, "minute_reset_at"),
            daily_reset_at=_payload_optional_datetime(payload, "daily_reset_at"),
            actual_prompt_tokens=_payload_optional_int(
                payload,
                "actual_prompt_tokens",
            ),
            actual_completion_tokens=_payload_optional_int(
                payload,
                "actual_completion_tokens",
            ),
            actual_total_tokens=_payload_optional_int(
                payload,
                "actual_total_tokens",
            ),
            outcome_class=_payload_text(payload, "outcome_class"),
            observed_at=_payload_datetime(payload, "observed_at"),
        )

    def to_event_payload(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "account_ref": self.account_ref,
            "model_ref": self.model_ref,
            "remaining_minute_requests": self.remaining_minute_requests,
            "remaining_minute_tokens": self.remaining_minute_tokens,
            "remaining_daily_requests": self.remaining_daily_requests,
            "remaining_daily_tokens": self.remaining_daily_tokens,
            "minute_reset_at": _datetime_payload(self.minute_reset_at),
            "daily_reset_at": _datetime_payload(self.daily_reset_at),
            "actual_prompt_tokens": self.actual_prompt_tokens,
            "actual_completion_tokens": self.actual_completion_tokens,
            "actual_total_tokens": self.actual_total_tokens,
            "outcome_class": self.outcome_class,
            "observed_at": self.observed_at.isoformat(),
        }


class LlmAttemptCapacityObservationRepositoryPort(Protocol):
    async def record_observation(
        self,
        observation: LlmAttemptCapacityObservation,
    ) -> None: ...

    async def observations_for_accounts_since(
        self,
        *,
        provider: str,
        account_refs: tuple[str, ...],
        model_ref: str,
        since: datetime,
    ) -> tuple[LlmAttemptCapacityObservation, ...]: ...


def _payload_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty str")
    return value


def _payload_optional_int(payload: Mapping[str, object], key: str) -> int | None:
    value = payload.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be non-negative int or None")
    return value


def _payload_datetime(payload: Mapping[str, object], key: str) -> datetime:
    value = payload.get(key)
    if not isinstance(value, datetime):
        raise ValueError(f"{key} must be datetime")
    _require_timezone_aware(value, key)
    return value


def _payload_optional_datetime(
    payload: Mapping[str, object],
    key: str,
) -> datetime | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise ValueError(f"{key} must be datetime or None")
    _require_timezone_aware(value, key)
    return value


def _datetime_payload(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _require_non_empty_text(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_negative_int(value: int, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{field_name} must be int")
    if value < 0:
        raise ValueError(f"{field_name} must be >= 0")


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
