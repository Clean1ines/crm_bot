from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import cast

import pytest

from src.contexts.capacity_runtime.application.ports.llm_attempt_capacity_observation_repository_port import (
    LlmAttemptCapacityObservation,
)
from src.contexts.capacity_runtime.infrastructure.postgres.postgres_llm_attempt_capacity_observation_repository import (
    PostgresLlmAttemptCapacityObservationRepository,
    observation_row_payload,
)


@dataclass(slots=True)
class FakeConnection:
    calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    async def execute(self, query: str, *args: object) -> str:
        self.calls.append((query, args))
        return "INSERT 0 1"


def _observed_at() -> datetime:
    return datetime(2026, 6, 13, 12, 0, tzinfo=timezone.utc)


def _observation(
    *,
    remaining_minute_requests: int | None = 10,
    remaining_minute_tokens: int | None = 1000,
    remaining_daily_requests: int | None = 200,
    remaining_daily_tokens: int | None = 20000,
    minute_reset_at: datetime | None = datetime(
        2026,
        6,
        13,
        12,
        1,
        tzinfo=timezone.utc,
    ),
    daily_reset_at: datetime | None = datetime(
        2026,
        6,
        14,
        0,
        0,
        tzinfo=timezone.utc,
    ),
    actual_prompt_tokens: int | None = 100,
    actual_completion_tokens: int | None = 20,
    actual_total_tokens: int | None = 120,
    outcome_class: str = "succeeded",
) -> LlmAttemptCapacityObservation:
    return LlmAttemptCapacityObservation(
        provider="groq",
        account_ref="groq_org_primary",
        model_ref="qwen/qwen3-32b",
        remaining_minute_requests=remaining_minute_requests,
        remaining_minute_tokens=remaining_minute_tokens,
        remaining_daily_requests=remaining_daily_requests,
        remaining_daily_tokens=remaining_daily_tokens,
        minute_reset_at=minute_reset_at,
        daily_reset_at=daily_reset_at,
        actual_prompt_tokens=actual_prompt_tokens,
        actual_completion_tokens=actual_completion_tokens,
        actual_total_tokens=actual_total_tokens,
        outcome_class=outcome_class,
        observed_at=_observed_at(),
    )


@pytest.mark.asyncio
async def test_record_observation_inserts_all_fields() -> None:
    connection = FakeConnection()
    observation = _observation()

    await PostgresLlmAttemptCapacityObservationRepository(
        connection,
    ).record_observation(observation)

    query, args = connection.calls[0]
    assert "INSERT INTO llm_attempt_capacity_observations" in query
    assert "ON CONFLICT (observation_id) DO UPDATE SET" in query
    assert args[0] == observation_row_payload(observation)["observation_id"]
    assert args[1:] == (
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


@pytest.mark.asyncio
async def test_record_observation_is_idempotent_for_same_observation() -> None:
    connection = FakeConnection()
    repository = PostgresLlmAttemptCapacityObservationRepository(connection)
    observation = _observation()

    await repository.record_observation(observation)
    await repository.record_observation(observation)

    assert connection.calls[0][1][0] == connection.calls[1][1][0]


@pytest.mark.asyncio
async def test_record_observation_updates_row_on_conflict() -> None:
    connection = FakeConnection()
    repository = PostgresLlmAttemptCapacityObservationRepository(connection)
    first = _observation(remaining_minute_requests=10)
    second = _observation(remaining_minute_requests=5)

    await repository.record_observation(first)
    await repository.record_observation(second)

    assert connection.calls[0][1][0] == connection.calls[1][1][0]
    assert connection.calls[1][1][4] == 5
    assert (
        "remaining_minute_requests = EXCLUDED.remaining_minute_requests"
        in (connection.calls[1][0])
    )


@pytest.mark.asyncio
async def test_nullable_remaining_reset_and_token_fields_persist_as_null() -> None:
    connection = FakeConnection()
    observation = _observation(
        remaining_minute_requests=None,
        remaining_minute_tokens=None,
        remaining_daily_requests=None,
        remaining_daily_tokens=None,
        minute_reset_at=None,
        daily_reset_at=None,
        actual_prompt_tokens=None,
        actual_completion_tokens=None,
        actual_total_tokens=None,
    )

    await PostgresLlmAttemptCapacityObservationRepository(
        connection,
    ).record_observation(observation)

    args = connection.calls[0][1]
    assert args[4:13] == (None, None, None, None, None, None, None, None, None)


@pytest.mark.asyncio
async def test_invalid_observation_type_raises_type_error() -> None:
    with pytest.raises(TypeError, match="LlmAttemptCapacityObservation"):
        await PostgresLlmAttemptCapacityObservationRepository(
            FakeConnection(),
        ).record_observation(cast(LlmAttemptCapacityObservation, object()))
