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
