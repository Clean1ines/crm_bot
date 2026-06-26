from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
    CapacityAdmissionSelectableWorkItem,
    CapacityAdmissionWindowBudget,
    SelectCapacityAdmissionWorkItem,
    SelectCapacityAdmissionWorkItemCommand,
)


def _lane() -> CapacityAdmissionLaneKey:
    return CapacityAdmissionLaneKey(
        work_kind="knowledge_workbench.draft_claim_compaction",
        provider="groq",
        account_ref="groq-account-1",
        model_ref="llama-3.3-70b-versatile",
    )


def _budget(tokens: int = 4096) -> CapacityAdmissionWindowBudget:
    return CapacityAdmissionWindowBudget(
        remaining_requests=1,
        remaining_tokens=tokens,
        remaining_daily_requests=10,
        remaining_daily_tokens=tokens,
    )


def _retryable_failed_item(
    work_item_id: str,
    *,
    tokens: int = 1024,
) -> CapacityAdmissionSelectableWorkItem:
    return CapacityAdmissionSelectableWorkItem(
        work_item_id=work_item_id,
        lane_key=_lane(),
        status="retryable_failed",
        required_window_tokens=tokens,
    )


def _ready_item(
    work_item_id: str,
    *,
    tokens: int = 1024,
) -> CapacityAdmissionSelectableWorkItem:
    return CapacityAdmissionSelectableWorkItem(
        work_item_id=work_item_id,
        lane_key=_lane(),
        status="ready",
        required_window_tokens=tokens,
    )


@dataclass(slots=True)
class FakeSelector:
    retryable_failed: CapacityAdmissionSelectableWorkItem | None = None
    ready: CapacityAdmissionSelectableWorkItem | None = None
    calls: list[str] = field(default_factory=list)
    max_token_limits: list[int] = field(default_factory=list)

    async def select_first_retryable_failed_fit(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        max_required_window_tokens: int,
    ) -> CapacityAdmissionSelectableWorkItem | None:
        assert lane_key == _lane()
        self.calls.append("retryable_failed")
        self.max_token_limits.append(max_required_window_tokens)
        return self.retryable_failed

    async def select_first_ready_fit(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        max_required_window_tokens: int,
    ) -> CapacityAdmissionSelectableWorkItem | None:
        assert lane_key == _lane()
        self.calls.append("ready")
        self.max_token_limits.append(max_required_window_tokens)
        return self.ready


@pytest.mark.asyncio
async def test_selects_retryable_failed_before_ready() -> None:
    retryable_failed = _retryable_failed_item("retryable-1")
    ready = _ready_item("ready-1")
    selector = FakeSelector(retryable_failed=retryable_failed, ready=ready)

    result = await SelectCapacityAdmissionWorkItem(selector).execute(
        SelectCapacityAdmissionWorkItemCommand(
            lane_key=_lane(),
            budget=_budget(),
        )
    )

    assert result.selected is True
    assert result.selected_work_item == retryable_failed
    assert result.skipped_reason is None
    assert selector.calls == ["retryable_failed"]


@pytest.mark.asyncio
async def test_falls_back_to_ready_when_no_retryable_failed_fits() -> None:
    ready = _ready_item("ready-1")
    selector = FakeSelector(ready=ready)

    result = await SelectCapacityAdmissionWorkItem(selector).execute(
        SelectCapacityAdmissionWorkItemCommand(
            lane_key=_lane(),
            budget=_budget(),
        )
    )

    assert result.selected_work_item == ready
    assert selector.calls == ["retryable_failed", "ready"]


@pytest.mark.asyncio
async def test_reports_no_fitting_work_item_when_lane_has_no_fit() -> None:
    selector = FakeSelector()

    result = await SelectCapacityAdmissionWorkItem(selector).execute(
        SelectCapacityAdmissionWorkItemCommand(
            lane_key=_lane(),
            budget=_budget(),
        )
    )

    assert result.selected is False
    assert result.selected_work_item is None
    assert result.skipped_reason == "no_fitting_work_item"
    assert selector.calls == ["retryable_failed", "ready"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("budget", "reason"),
    [
        (
            CapacityAdmissionWindowBudget(
                remaining_requests=0,
                remaining_tokens=4096,
                remaining_daily_requests=10,
                remaining_daily_tokens=4096,
            ),
            "capacity_exhausted",
        ),
        (
            CapacityAdmissionWindowBudget(
                remaining_requests=1,
                remaining_tokens=0,
                remaining_daily_requests=10,
                remaining_daily_tokens=4096,
            ),
            "capacity_exhausted",
        ),
        (
            CapacityAdmissionWindowBudget(
                remaining_requests=1,
                remaining_tokens=4096,
                remaining_daily_requests=0,
                remaining_daily_tokens=4096,
            ),
            "capacity_exhausted",
        ),
        (
            CapacityAdmissionWindowBudget(
                remaining_requests=1,
                remaining_tokens=4096,
                remaining_daily_requests=10,
                remaining_daily_tokens=0,
            ),
            "capacity_exhausted",
        ),
    ],
)
async def test_does_not_query_repository_when_capacity_is_exhausted(
    budget: CapacityAdmissionWindowBudget,
    reason: str,
) -> None:
    selector = FakeSelector(
        retryable_failed=_retryable_failed_item("retryable-1"),
        ready=_ready_item("ready-1"),
    )

    result = await SelectCapacityAdmissionWorkItem(selector).execute(
        SelectCapacityAdmissionWorkItemCommand(
            lane_key=_lane(),
            budget=budget,
        )
    )

    assert result.selected is False
    assert result.skipped_reason == reason
    assert selector.calls == []


@pytest.mark.asyncio
async def test_passes_minute_and_daily_token_floor_as_fit_limit() -> None:
    selector = FakeSelector(ready=_ready_item("ready-1"))

    result = await SelectCapacityAdmissionWorkItem(selector).execute(
        SelectCapacityAdmissionWorkItemCommand(
            lane_key=_lane(),
            budget=CapacityAdmissionWindowBudget(
                remaining_requests=1,
                remaining_tokens=8000,
                remaining_daily_requests=10,
                remaining_daily_tokens=3000,
            ),
        )
    )

    assert result.selected_work_item is not None
    assert selector.max_token_limits == [3000, 3000]


def test_rejects_negative_budget_values() -> None:
    with pytest.raises(ValueError, match="remaining_requests"):
        CapacityAdmissionWindowBudget(
            remaining_requests=-1,
            remaining_tokens=1,
            remaining_daily_requests=1,
            remaining_daily_tokens=1,
        )
