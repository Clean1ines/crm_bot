from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol, cast

import asyncpg

from src.contexts.capacity_admission_queue.application.admit_capacity_admission_work_item import (
    CapacityAdmissionProjectionLeaseResult,
)
from src.contexts.capacity_admission_queue.application.lease_selected_capacity_admission_work_item import (
    LeaseSelectedCapacityAdmissionWorkItem,
    LeaseSelectedCapacityAdmissionWorkItemCommand,
)
from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
    CapacityAdmissionSelectableWorkItem,
    CapacityAdmissionWindowBudget,
    SelectCapacityAdmissionWorkItem,
    SelectCapacityAdmissionWorkItemCommand,
)
from src.contexts.capacity_admission_queue.infrastructure.postgres.postgres_capacity_admission_projection_admitter import (
    PostgresCapacityAdmissionProjectionAdmitter,
)
from src.contexts.capacity_admission_queue.infrastructure.postgres.postgres_capacity_admission_work_item_selector import (
    PostgresCapacityAdmissionWorkItemSelector,
)
from src.contexts.execution_runtime.application.ports.work_item_lease_repository_port import (
    LeasedWorkItemRecord,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_lease_repository import (
    PostgresWorkItemLeaseRepository,
)


class AsyncCapacityAdmissionPoolLike(Protocol):
    async def acquire(self) -> object: ...

    async def release(self, connection: object) -> None: ...


@dataclass(frozen=True, slots=True)
class RunCapacityAdmissionWorkItemAdmissionCommand:
    lane_key: CapacityAdmissionLaneKey
    budget: CapacityAdmissionWindowBudget
    worker: WorkerRef
    lease_token: LeaseToken
    lease_expires_at: datetime
    now: datetime

    def __post_init__(self) -> None:
        _require_timezone_aware(self.lease_expires_at, "lease_expires_at")
        _require_timezone_aware(self.now, "now")
        if self.lease_expires_at <= self.now:
            raise ValueError("lease_expires_at must be after now")


@dataclass(frozen=True, slots=True)
class RunCapacityAdmissionWorkItemAdmissionResult:
    selected_work_item: CapacityAdmissionSelectableWorkItem | None
    execution_lease: LeasedWorkItemRecord | None
    projection_lease: CapacityAdmissionProjectionLeaseResult | None
    skipped_reason: str | None = None

    @property
    def leased(self) -> bool:
        return self.execution_lease is not None and self.projection_lease is not None


@dataclass(frozen=True, slots=True)
class RunCapacityAdmissionWorkItemAdmission:
    pool: AsyncCapacityAdmissionPoolLike

    async def execute(
        self,
        command: RunCapacityAdmissionWorkItemAdmissionCommand,
    ) -> RunCapacityAdmissionWorkItemAdmissionResult:
        connection = await self.pool.acquire()
        try:
            asyncpg_connection = cast(asyncpg.Connection, connection)
            async with asyncpg_connection.transaction():
                selection = await SelectCapacityAdmissionWorkItem(
                    PostgresCapacityAdmissionWorkItemSelector(asyncpg_connection)
                ).execute(
                    SelectCapacityAdmissionWorkItemCommand(
                        lane_key=command.lane_key,
                        budget=command.budget,
                    )
                )
                if selection.selected_work_item is None:
                    return RunCapacityAdmissionWorkItemAdmissionResult(
                        selected_work_item=None,
                        execution_lease=None,
                        projection_lease=None,
                        skipped_reason=selection.skipped_reason,
                    )

                lease_result = await LeaseSelectedCapacityAdmissionWorkItem(
                    execution_lease_repository=PostgresWorkItemLeaseRepository(
                        asyncpg_connection
                    ),
                    projection_admitter=PostgresCapacityAdmissionProjectionAdmitter(
                        asyncpg_connection
                    ),
                ).execute(
                    LeaseSelectedCapacityAdmissionWorkItemCommand(
                        selected_work_item=selection.selected_work_item,
                        worker=command.worker,
                        lease_token=command.lease_token,
                        lease_expires_at=command.lease_expires_at,
                        now=command.now,
                    )
                )

                return RunCapacityAdmissionWorkItemAdmissionResult(
                    selected_work_item=selection.selected_work_item,
                    execution_lease=lease_result.execution_lease,
                    projection_lease=lease_result.projection_lease,
                    skipped_reason=lease_result.skipped_reason,
                )
        finally:
            await self.pool.release(connection)


def build_capacity_admission_work_item_admission_runner(
    pool: object,
) -> RunCapacityAdmissionWorkItemAdmission:
    return RunCapacityAdmissionWorkItemAdmission(
        pool=cast(AsyncCapacityAdmissionPoolLike, pool),
    )


def _require_timezone_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
