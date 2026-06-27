from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol


CapacityAdmissionProjectionStatus = Literal["retryable_failed", "ready"]


@dataclass(frozen=True, slots=True)
class CapacityAdmissionLaneKey:
    work_kind: str
    provider: str
    model_ref: str
    account_ref: str | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.work_kind, "work_kind")
        _require_non_empty(self.provider, "provider")
        _require_non_empty(self.model_ref, "model_ref")
        if self.account_ref is not None:
            _require_non_empty(self.account_ref, "account_ref")


@dataclass(frozen=True, slots=True)
class CapacityAdmissionWindowBudget:
    remaining_requests: int
    remaining_tokens: int
    remaining_daily_requests: int
    remaining_daily_tokens: int

    def __post_init__(self) -> None:
        _require_non_negative(self.remaining_requests, "remaining_requests")
        _require_non_negative(self.remaining_tokens, "remaining_tokens")
        _require_non_negative(
            self.remaining_daily_requests,
            "remaining_daily_requests",
        )
        _require_non_negative(self.remaining_daily_tokens, "remaining_daily_tokens")

    @property
    def admits_any_work(self) -> bool:
        return (
            self.remaining_requests > 0
            and self.remaining_tokens > 0
            and self.remaining_daily_requests > 0
            and self.remaining_daily_tokens > 0
        )

    @property
    def max_required_window_tokens(self) -> int:
        return min(self.remaining_tokens, self.remaining_daily_tokens)


@dataclass(frozen=True, slots=True)
class CapacityAdmissionSelectableWorkItem:
    work_item_id: str
    lane_key: CapacityAdmissionLaneKey
    status: CapacityAdmissionProjectionStatus
    required_window_tokens: int
    input_tokens: int | None = None
    artifact_tokens: int | None = None

    def __post_init__(self) -> None:
        _require_non_empty(self.work_item_id, "work_item_id")
        _require_positive(self.required_window_tokens, "required_window_tokens")
        if self.input_tokens is not None:
            _require_positive(self.input_tokens, "input_tokens")
        if self.artifact_tokens is not None:
            _require_non_negative(
                self.artifact_tokens,
                "artifact_tokens",
            )


@dataclass(frozen=True, slots=True)
class SelectCapacityAdmissionWorkItemCommand:
    lane_key: CapacityAdmissionLaneKey
    budget: CapacityAdmissionWindowBudget


@dataclass(frozen=True, slots=True)
class SelectCapacityAdmissionWorkItemResult:
    selected_work_item: CapacityAdmissionSelectableWorkItem | None
    skipped_reason: str | None = None

    @property
    def selected(self) -> bool:
        return self.selected_work_item is not None


class CapacityAdmissionWorkItemSelectorPort(Protocol):
    async def select_first_retryable_failed_fit(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        max_required_window_tokens: int,
    ) -> CapacityAdmissionSelectableWorkItem | None:
        """Return the first fitting retryable failed item inside one lane."""

    async def select_first_ready_fit(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        max_required_window_tokens: int,
    ) -> CapacityAdmissionSelectableWorkItem | None:
        """Return the first fitting ready item inside one lane."""


@dataclass(frozen=True, slots=True)
class SelectCapacityAdmissionWorkItem:
    selector: CapacityAdmissionWorkItemSelectorPort

    async def execute(
        self,
        command: SelectCapacityAdmissionWorkItemCommand,
    ) -> SelectCapacityAdmissionWorkItemResult:
        if not command.budget.admits_any_work:
            return SelectCapacityAdmissionWorkItemResult(
                selected_work_item=None,
                skipped_reason="capacity_exhausted",
            )

        max_required_window_tokens = command.budget.max_required_window_tokens

        retryable_failed = await self.selector.select_first_retryable_failed_fit(
            lane_key=command.lane_key,
            max_required_window_tokens=max_required_window_tokens,
        )
        if retryable_failed is not None:
            return SelectCapacityAdmissionWorkItemResult(
                selected_work_item=retryable_failed,
            )

        ready = await self.selector.select_first_ready_fit(
            lane_key=command.lane_key,
            max_required_window_tokens=max_required_window_tokens,
        )
        if ready is not None:
            return SelectCapacityAdmissionWorkItemResult(
                selected_work_item=ready,
            )

        return SelectCapacityAdmissionWorkItemResult(
            selected_work_item=None,
            skipped_reason="no_fitting_work_item",
        )


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} must not be empty")


def _require_non_negative(value: int, field_name: str) -> None:
    if value < 0:
        raise ValueError(f"{field_name} must be non-negative")


def _require_positive(value: int, field_name: str) -> None:
    if value <= 0:
        raise ValueError(f"{field_name} must be positive")
