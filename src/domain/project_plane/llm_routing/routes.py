from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .shared import (
    ApiKeySlot,
    ModelName,
    OperationName,
    ProviderId,
    RouteChainId,
    require_non_empty,
    require_non_negative_int,
)


class LlmRouteAttemptStatus(StrEnum):
    PLANNED = "planned"
    STARTED = "started"
    SUCCESS = "success"
    SKIPPED = "skipped"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class LlmRouteAttempt:
    provider_id: ProviderId
    model: ModelName
    api_key_slot: ApiKeySlot
    attempt_index: int
    status: LlmRouteAttemptStatus = LlmRouteAttemptStatus.PLANNED
    error_kind: str | None = None
    cooldown_seconds: int | None = None

    def __post_init__(self) -> None:
        require_non_empty(self.provider_id, field_name="provider_id")
        require_non_empty(self.model, field_name="model")
        require_non_empty(self.api_key_slot, field_name="api_key_slot")
        require_non_negative_int(self.attempt_index, field_name="attempt_index")
        if self.cooldown_seconds is not None:
            require_non_negative_int(
                self.cooldown_seconds,
                field_name="cooldown_seconds",
            )


@dataclass(frozen=True, slots=True)
class LlmRoutePlan:
    route_chain_id: RouteChainId
    operation_name: OperationName
    attempts: tuple[LlmRouteAttempt, ...]

    def __post_init__(self) -> None:
        require_non_empty(self.route_chain_id, field_name="route_chain_id")
        require_non_empty(self.operation_name, field_name="operation_name")
        if not self.attempts:
            raise ValueError("route plan requires at least one attempt")
        expected_indexes = tuple(range(len(self.attempts)))
        actual_indexes = tuple(attempt.attempt_index for attempt in self.attempts)
        if actual_indexes != expected_indexes:
            raise ValueError("route attempt indexes must be contiguous from zero")

    @property
    def route_chain(self) -> tuple[str, ...]:
        return tuple(
            f"{attempt.provider_id}:{attempt.model}:{attempt.api_key_slot}"
            for attempt in self.attempts
        )
