from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CapacityAdmissionLaneKey:
    work_kind: str
    provider: str
    account_ref: str | None
    model_ref: str


@dataclass(frozen=True, slots=True)
class CapacityAdmissionWindowBudget:
    remaining_request_count: int | None = None
    remaining_input_tokens: int | None = None
    remaining_output_tokens: int | None = None
    remaining_total_tokens: int | None = None
    reset_at: object | None = None


@dataclass(frozen=True, slots=True)
class CapacityAdmissionSelectableWorkItem:
    work_item_id: str
    work_kind: str
    payload: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class SelectCapacityAdmissionWorkItemCommand:
    lane_key: CapacityAdmissionLaneKey
    window_budget: CapacityAdmissionWindowBudget


@dataclass(frozen=True, slots=True)
class SelectCapacityAdmissionWorkItemResult:
    selected_work_item: CapacityAdmissionSelectableWorkItem | None = None
    skipped_reason: str | None = "capacity_admission_disabled"


class SelectCapacityAdmissionWorkItem:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def execute(
        self,
        command: SelectCapacityAdmissionWorkItemCommand,
    ) -> SelectCapacityAdmissionWorkItemResult:
        return SelectCapacityAdmissionWorkItemResult()
