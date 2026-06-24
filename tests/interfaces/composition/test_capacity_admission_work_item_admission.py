from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
    CapacityAdmissionWindowBudget,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.interfaces.composition.capacity_admission_work_item_admission import (
    RunCapacityAdmissionWorkItemAdmissionCommand,
)

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "src/interfaces/composition/capacity_admission_work_item_admission.py"


def _source() -> str:
    return SOURCE.read_text(encoding="utf-8")


def _now() -> datetime:
    return datetime(2026, 6, 24, 12, 0, tzinfo=timezone.utc)


def _lane() -> CapacityAdmissionLaneKey:
    return CapacityAdmissionLaneKey(
        work_kind="knowledge.claim_builder",
        provider="groq",
        account_ref="groq-account-1",
        model_ref="llama-3.3-70b-versatile",
    )


def _budget() -> CapacityAdmissionWindowBudget:
    return CapacityAdmissionWindowBudget(
        remaining_requests=1,
        remaining_tokens=4096,
        remaining_daily_requests=10,
        remaining_daily_tokens=4096,
    )


def test_runner_owns_single_transaction_for_selector_and_admission() -> None:
    source = _source()

    assert "connection = await self.pool.acquire()" in source
    assert "async with asyncpg_connection.transaction():" in source
    assert "await self.pool.release(connection)" in source
    execute_body = source[source.index("    async def execute(") :]
    assert execute_body.index(
        "PostgresCapacityAdmissionWorkItemSelector"
    ) < execute_body.index("LeaseSelectedCapacityAdmissionWorkItem")


def test_runner_wires_capacity_selector_execution_lease_and_projection_admitter() -> (
    None
):
    source = _source()

    assert "SelectCapacityAdmissionWorkItem(" in source
    assert "PostgresCapacityAdmissionWorkItemSelector(asyncpg_connection)" in source
    assert "LeaseSelectedCapacityAdmissionWorkItem(" in source
    assert "PostgresWorkItemLeaseRepository(" in source
    assert "PostgresCapacityAdmissionProjectionAdmitter(" in source
    assert "LeaseSelectedCapacityAdmissionWorkItemCommand(" in source


def test_runner_returns_selection_skip_before_execution_lease() -> None:
    source = _source()

    assert "if selection.selected_work_item is None:" in source
    assert source.index("if selection.selected_work_item is None:") < source.index(
        "PostgresWorkItemLeaseRepository("
    )


def test_build_capacity_admission_runner_casts_pool_protocol() -> None:
    source = _source()

    assert "build_capacity_admission_work_item_admission_runner" in source
    assert "cast(AsyncCapacityAdmissionPoolLike, pool)" in source


def test_command_rejects_naive_timestamps() -> None:
    with pytest.raises(ValueError, match="now"):
        RunCapacityAdmissionWorkItemAdmissionCommand(
            lane_key=_lane(),
            budget=_budget(),
            worker=WorkerRef("capacity-admission-worker-1"),
            lease_token=LeaseToken("lease-token-1"),
            lease_expires_at=_now() + timedelta(minutes=5),
            now=datetime(2026, 6, 24, 12, 0),
        )


def test_command_rejects_expired_lease_deadline() -> None:
    with pytest.raises(ValueError, match="lease_expires_at must be after now"):
        RunCapacityAdmissionWorkItemAdmissionCommand(
            lane_key=_lane(),
            budget=_budget(),
            worker=WorkerRef("capacity-admission-worker-1"),
            lease_token=LeaseToken("lease-token-1"),
            lease_expires_at=_now(),
            now=_now(),
        )
