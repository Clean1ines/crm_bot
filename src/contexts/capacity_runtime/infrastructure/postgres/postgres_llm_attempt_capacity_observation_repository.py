from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from hashlib import sha256
from typing import Protocol

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservation,
    LlmAttemptCapacityObservationRepositoryPort,
)


class LlmAttemptCapacityObservationConnectionLike(Protocol):
    async def execute(self, query: str, *args: object) -> str: ...

    async def fetch(self, query: str, *args: object) -> list[Mapping[str, object]]: ...


class PostgresLlmAttemptCapacityObservationRepository(
    LlmAttemptCapacityObservationRepositoryPort,
):
    """Persists provider/model capacity observations inside the caller transaction."""

    def __init__(self, connection: LlmAttemptCapacityObservationConnectionLike) -> None:
        self._connection = connection

    async def record_observation(
        self,
        observation: LlmAttemptCapacityObservation,
    ) -> None:
        if not isinstance(observation, LlmAttemptCapacityObservation):
            raise TypeError("observation must be LlmAttemptCapacityObservation")

        await self._connection.execute(
            """
            INSERT INTO llm_attempt_capacity_observations (
                observation_id,
                provider,
                account_ref,
                model_ref,
                remaining_minute_requests,
                remaining_minute_tokens,
                remaining_daily_requests,
                remaining_daily_tokens,
                minute_reset_at,
                daily_reset_at,
                actual_prompt_tokens,
                actual_completion_tokens,
                actual_total_tokens,
                outcome_class,
                observed_at
            )
            VALUES (
                $1, $2, $3, $4, $5,
                $6, $7, $8, $9, $10,
                $11, $12, $13, $14, $15
            )
            ON CONFLICT (observation_id) DO UPDATE SET
                provider = EXCLUDED.provider,
                account_ref = EXCLUDED.account_ref,
                model_ref = EXCLUDED.model_ref,
                remaining_minute_requests = EXCLUDED.remaining_minute_requests,
                remaining_minute_tokens = EXCLUDED.remaining_minute_tokens,
                remaining_daily_requests = EXCLUDED.remaining_daily_requests,
                remaining_daily_tokens = EXCLUDED.remaining_daily_tokens,
                minute_reset_at = EXCLUDED.minute_reset_at,
                daily_reset_at = EXCLUDED.daily_reset_at,
                actual_prompt_tokens = EXCLUDED.actual_prompt_tokens,
                actual_completion_tokens = EXCLUDED.actual_completion_tokens,
                actual_total_tokens = EXCLUDED.actual_total_tokens,
                outcome_class = EXCLUDED.outcome_class,
                observed_at = EXCLUDED.observed_at
            """,
            _observation_id(observation),
            observation.provider,
            observation.account_ref,
            observation.model_ref,
            observation.remaining_minute_requests,
            observation.remaining_minute_tokens,
            observation.remaining_daily_requests,
            observation.remaining_daily_tokens,
            observation.minute_reset_at,
            observation.daily_reset_at,
            observation.actual_prompt_tokens,
            observation.actual_completion_tokens,
            observation.actual_total_tokens,
            observation.outcome_class,
            observation.observed_at,
        )

    async def latest_observations_for_accounts(
        self,
        *,
        provider: str,
        account_refs: tuple[str, ...],
        model_ref: str,
    ) -> tuple[LlmAttemptCapacityObservation, ...]:
        _require_non_empty_text(provider, field_name="provider")
        _require_non_empty_text(model_ref, field_name="model_ref")
        _require_non_empty_text_tuple(account_refs, field_name="account_refs")

        rows = await self._connection.fetch(
            """
            SELECT DISTINCT ON (provider, account_ref, model_ref)
                provider,
                account_ref,
                model_ref,
                remaining_minute_requests,
                remaining_minute_tokens,
                remaining_daily_requests,
                remaining_daily_tokens,
                minute_reset_at,
                daily_reset_at,
                actual_prompt_tokens,
                actual_completion_tokens,
                actual_total_tokens,
                outcome_class,
                observed_at
            FROM llm_attempt_capacity_observations
            WHERE provider = $1
              AND model_ref = $2
              AND account_ref = ANY($3::text[])
            ORDER BY provider, account_ref, model_ref, observed_at DESC
            """,
            provider,
            model_ref,
            list(account_refs),
        )
        return tuple(_observation_from_row(row) for row in rows)


def _observation_from_row(
    row: Mapping[str, object],
) -> LlmAttemptCapacityObservation:
    return LlmAttemptCapacityObservation(
        provider=_row_text(row, "provider"),
        account_ref=_row_text(row, "account_ref"),
        model_ref=_row_text(row, "model_ref"),
        remaining_minute_requests=_row_optional_int(
            row,
            "remaining_minute_requests",
        ),
        remaining_minute_tokens=_row_optional_int(
            row,
            "remaining_minute_tokens",
        ),
        remaining_daily_requests=_row_optional_int(
            row,
            "remaining_daily_requests",
        ),
        remaining_daily_tokens=_row_optional_int(
            row,
            "remaining_daily_tokens",
        ),
        minute_reset_at=_row_optional_datetime(row, "minute_reset_at"),
        daily_reset_at=_row_optional_datetime(row, "daily_reset_at"),
        actual_prompt_tokens=_row_optional_int(row, "actual_prompt_tokens"),
        actual_completion_tokens=_row_optional_int(
            row,
            "actual_completion_tokens",
        ),
        actual_total_tokens=_row_optional_int(row, "actual_total_tokens"),
        outcome_class=_row_text(row, "outcome_class"),
        observed_at=_row_datetime(row, "observed_at"),
    )


def _row_text(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be non-empty text")
    return value


def _row_optional_int(row: Mapping[str, object], key: str) -> int | None:
    value = row.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be non-negative int or None")
    return value


def _row_datetime(row: Mapping[str, object], key: str) -> datetime:
    value = row.get(key)
    if not isinstance(value, datetime):
        raise ValueError(f"{key} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{key} must be timezone-aware")
    return value


def _row_optional_datetime(
    row: Mapping[str, object],
    key: str,
) -> datetime | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise ValueError(f"{key} must be datetime or None")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{key} must be timezone-aware")
    return value


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_non_empty_text_tuple(
    value: tuple[str, ...],
    *,
    field_name: str,
) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    if not value:
        raise ValueError(f"{field_name} must be non-empty")
    for item in value:
        _require_non_empty_text(item, field_name=field_name)


def _observation_id(observation: LlmAttemptCapacityObservation) -> str:
    digest = sha256(
        _observation_identity_payload(observation).encode("utf-8"),
    ).hexdigest()
    return f"llm-attempt-capacity-observation:{digest}"


def _observation_identity_payload(
    observation: LlmAttemptCapacityObservation,
) -> str:
    parts = (
        observation.provider,
        observation.account_ref,
        observation.model_ref,
        _datetime_identity(observation.observed_at),
        observation.outcome_class,
        _optional_int_identity(observation.actual_total_tokens),
    )
    return "|".join(parts)


def _datetime_identity(value: datetime) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")
    return value.astimezone(timezone.utc).isoformat()


def _optional_int_identity(value: int | None) -> str:
    if value is None:
        return "none"
    return str(value)


def observation_row_payload(
    observation: LlmAttemptCapacityObservation,
) -> Mapping[str, object]:
    """Small test seam for checking the deterministic observation identity."""

    return {
        "observation_id": _observation_id(observation),
        "provider": observation.provider,
        "account_ref": observation.account_ref,
        "model_ref": observation.model_ref,
        "outcome_class": observation.outcome_class,
        "observed_at": observation.observed_at,
    }
