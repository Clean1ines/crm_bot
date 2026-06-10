from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from types import TracebackType
from typing import Protocol, cast

import asyncpg

from src.contexts.capacity_runtime.domain.capacity_policy import CapacityAdmissionPolicy
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_attempt_dispatch_repository import (
    PostgresWorkItemAttemptDispatchRepository,
)
from src.contexts.execution_runtime.infrastructure.postgres.postgres_work_item_lease_repository import (
    PostgresWorkItemLeaseRepository,
)
from src.contexts.llm_runtime.application.capacity.select_active_llm_model_capacity import (
    SelectActiveLlmModelCapacity,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    LlmModelRouteCatalog,
)
from src.contexts.llm_runtime.domain.capacity.llm_provider_account_capacity import (
    LlmProviderAccountCapacity,
)
from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)
from src.interfaces.composition.lease_llm_admitted_work_items import (
    LeaseLlmAdmittedWorkItems,
    LeaseLlmAdmittedWorkItemsCommand,
    LeaseLlmAdmittedWorkItemsResult,
)
from src.interfaces.composition.start_llm_admitted_work_item_attempts import (
    StartLlmAdmittedWorkItemAttempts,
    StartLlmAdmittedWorkItemAttemptsCommand,
    StartLlmAdmittedWorkItemAttemptsResult,
)


class AsyncTransaction(Protocol):
    async def __aenter__(self) -> object: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...


class AsyncConnection(Protocol):
    def transaction(self) -> AsyncTransaction: ...


class AsyncPool(Protocol):
    async def acquire(self) -> AsyncConnection: ...

    async def release(self, connection: AsyncConnection) -> None: ...


@dataclass(frozen=True, slots=True)
class PrepareLlmDispatchBatchCommand:
    work_kind: WorkKind
    profile: LlmTaskCapacityProfile
    account_capacities: tuple[LlmProviderAccountCapacity, ...]
    active_model_ref: str
    requested_items: int
    worker: WorkerRef
    lease_token_prefix: str
    lease_expires_at: datetime
    now: datetime
    started_at: datetime

    def __post_init__(self) -> None:
        LeaseLlmAdmittedWorkItemsCommand(
            work_kind=self.work_kind,
            profile=self.profile,
            account_capacities=self.account_capacities,
            active_model_ref=self.active_model_ref,
            requested_items=self.requested_items,
            worker=self.worker,
            lease_token_prefix=self.lease_token_prefix,
            lease_expires_at=self.lease_expires_at,
            now=self.now,
        )
        _require_timezone_aware(self.started_at, field_name="started_at")
        if self.started_at < self.now:
            raise ValueError("started_at must be >= now")


@dataclass(frozen=True, slots=True)
class PrepareLlmDispatchBatchResult:
    lease_result: LeaseLlmAdmittedWorkItemsResult
    attempt_result: StartLlmAdmittedWorkItemAttemptsResult

    def __post_init__(self) -> None:
        if not isinstance(self.lease_result, LeaseLlmAdmittedWorkItemsResult):
            raise TypeError("lease_result must be LeaseLlmAdmittedWorkItemsResult")
        if not isinstance(
            self.attempt_result,
            StartLlmAdmittedWorkItemAttemptsResult,
        ):
            raise TypeError(
                "attempt_result must be StartLlmAdmittedWorkItemAttemptsResult",
            )
        if len(self.attempt_result.started_attempts) != len(self.lease_result.leased):
            raise ValueError("started attempt count must equal leased item count")


@dataclass(frozen=True, slots=True)
class PrepareLlmDispatchBatch:
    pool: AsyncPool
    capacity_policy: CapacityAdmissionPolicy
    active_model_capacity_selector: SelectActiveLlmModelCapacity
    route_catalog: LlmModelRouteCatalog

    def __post_init__(self) -> None:
        if not isinstance(self.route_catalog, LlmModelRouteCatalog):
            raise TypeError("route_catalog must be LlmModelRouteCatalog")

    async def execute(
        self,
        command: PrepareLlmDispatchBatchCommand,
    ) -> PrepareLlmDispatchBatchResult:
        connection = await self.pool.acquire()
        try:
            async with connection.transaction():
                asyncpg_connection = cast(asyncpg.Connection, connection)
                lease_repository = PostgresWorkItemLeaseRepository(asyncpg_connection)
                attempt_repository = PostgresWorkItemAttemptDispatchRepository(
                    asyncpg_connection,
                )

                lease_result = await LeaseLlmAdmittedWorkItems(
                    lease_repository=lease_repository,
                    capacity_policy=self.capacity_policy,
                    active_model_capacity_selector=self.active_model_capacity_selector,
                    route_catalog=self.route_catalog,
                ).execute(
                    LeaseLlmAdmittedWorkItemsCommand(
                        work_kind=command.work_kind,
                        profile=command.profile,
                        account_capacities=command.account_capacities,
                        active_model_ref=command.active_model_ref,
                        requested_items=command.requested_items,
                        worker=command.worker,
                        lease_token_prefix=command.lease_token_prefix,
                        lease_expires_at=command.lease_expires_at,
                        now=command.now,
                    ),
                )

                attempt_result = await StartLlmAdmittedWorkItemAttempts(
                    repository=attempt_repository,
                ).execute(
                    StartLlmAdmittedWorkItemAttemptsCommand(
                        leased_items=lease_result.leased,
                        started_at=command.started_at,
                    ),
                )

                return PrepareLlmDispatchBatchResult(
                    lease_result=lease_result,
                    attempt_result=attempt_result,
                )
        finally:
            await self.pool.release(connection)


def _require_timezone_aware(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
