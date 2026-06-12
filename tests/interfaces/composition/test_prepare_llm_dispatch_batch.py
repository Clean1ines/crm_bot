from __future__ import annotations

import copy
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from types import TracebackType
from typing import Self

import pytest

from src.contexts.capacity_runtime.domain.capacity_policy import CapacityAdmissionPolicy
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.llm_runtime.application.capacity.project_llm_capacity_to_capacity_runtime import (
    ProjectLlmCapacityToCapacityRuntime,
)
from src.contexts.llm_runtime.application.capacity.select_active_llm_model_capacity import (
    SelectActiveLlmModelCapacity,
)
from src.contexts.llm_runtime.domain.capacity.llm_provider_account_capacity import (
    LlmProviderAccountCapacity,
)
from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)
from src.contexts.llm_runtime.domain.capacity.llm_model_route_catalog import (
    default_groq_llm_model_route_catalog,
)
from src.interfaces.composition.prepare_llm_dispatch_batch import (
    PrepareLlmDispatchBatch,
    PrepareLlmDispatchBatchCommand,
)


class DispatchInsertError(RuntimeError):
    pass


@dataclass(slots=True)
class FakeTransaction:
    connection: FakeConnection
    entered: bool = False
    exit_exc_type: type[BaseException] | None = None
    committed: bool = False
    rolled_back: bool = False
    _snapshot: dict[str, object] | None = None

    async def __aenter__(self) -> Self:
        self.entered = True
        self._snapshot = {
            "work_items": copy.deepcopy(self.connection.work_items),
            "attempts": copy.deepcopy(self.connection.attempts),
            "dispatches": copy.deepcopy(self.connection.dispatches),
        }
        self.connection.transactions.append(self)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None:
        self.exit_exc_type = exc_type
        if exc_type is None:
            self.committed = True
            return None

        self.rolled_back = True
        if self._snapshot is None:
            raise RuntimeError("transaction snapshot missing")
        self.connection.work_items = copy.deepcopy(self._snapshot["work_items"])
        self.connection.attempts = copy.deepcopy(self._snapshot["attempts"])
        self.connection.dispatches = copy.deepcopy(self._snapshot["dispatches"])
        return None


@dataclass(slots=True)
class FakeConnection:
    work_items: dict[str, dict[str, object]] = field(default_factory=dict)
    schedules: dict[str, dict[str, object]] = field(default_factory=dict)
    attempts: dict[str, dict[str, object]] = field(default_factory=dict)
    dispatches: dict[str, dict[str, object]] = field(default_factory=dict)
    transactions: list[FakeTransaction] = field(default_factory=list)
    fail_dispatch_insert: bool = False

    def transaction(self) -> FakeTransaction:
        return FakeTransaction(connection=self)

    async def fetchrow(self, query: str, *args: object) -> dict[str, object] | None:
        work_kind = str(args[0])
        now = _as_datetime(args[1])
        candidates: list[dict[str, object]] = []

        for row in self.work_items.values():
            if row["work_kind"] != work_kind:
                continue
            if row["status"] not in {"ready", "deferred", "retryable_failed"}:
                continue
            next_attempt_at = row["next_attempt_at"]
            if next_attempt_at is not None and _as_datetime(next_attempt_at) > now:
                continue
            work_item_id = str(row["work_item_id"])
            payload = self.schedules.get(work_item_id)
            if payload is None:
                continue
            candidates.append({**row, "payload": payload})

        candidates.sort(
            key=lambda row: (
                row["next_attempt_at"] is not None,
                row["next_attempt_at"] or datetime.min.replace(tzinfo=timezone.utc),
                row["updated_at"],
                row["work_item_id"],
            ),
        )
        return candidates[0] if candidates else None

    async def execute(self, query: str, *args: object) -> str:
        if "UPDATE execution_work_items" in query:
            work_item_id = str(args[0])
            row = self.work_items[work_item_id]
            row["status"] = args[1]
            row["attempt_count"] = args[2]
            row["leased_by"] = args[3]
            row["lease_token"] = args[4]
            row["lease_expires_at"] = args[5]
            row["next_attempt_at"] = None
            row["last_error_kind"] = None
            row["updated_at"] = args[6]
            return "UPDATE 1"

        if "INSERT INTO execution_work_item_attempts" in query:
            self.attempts[str(args[0])] = {
                "attempt_id": args[0],
                "work_item_id": args[1],
                "attempt_number": args[2],
                "started_at": args[3],
            }
            return "INSERT 0 1"

        if "INSERT INTO execution_work_item_attempt_dispatches" in query:
            if self.fail_dispatch_insert:
                raise DispatchInsertError("dispatch insert failed")
            self.dispatches[str(args[0])] = {
                "attempt_id": args[0],
                "work_item_id": args[1],
                "attempt_number": args[2],
                "lease_token": args[3],
                "worker_ref": args[4],
                "schedule_payload": json.loads(str(args[5])),
                "llm_allocation_payload": json.loads(str(args[6])),
                "dispatch_payload": json.loads(str(args[7])),
            }
            return "INSERT 0 1"

        raise AssertionError(f"unexpected query: {query}")


@dataclass(slots=True)
class FakePool:
    connection: FakeConnection
    released: list[FakeConnection] = field(default_factory=list)

    async def acquire(self) -> FakeConnection:
        return self.connection

    async def release(self, connection: FakeConnection) -> None:
        self.released.append(connection)


def _now() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _lease_expires_at() -> datetime:
    return datetime(2026, 6, 10, 12, 5, tzinfo=timezone.utc)


def _started_at() -> datetime:
    return datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc)


def _updated_at(minutes: int) -> datetime:
    return datetime(2026, 6, 10, 11, minutes, tzinfo=timezone.utc)


def _work_kind() -> WorkKind:
    return WorkKind("knowledge_workbench.claim_builder.section_extraction")


def _worker() -> WorkerRef:
    return WorkerRef("worker-1")


def _profile() -> LlmTaskCapacityProfile:
    return LlmTaskCapacityProfile(
        profile_id="prompt-a",
        estimated_prompt_tokens=3000,
        estimated_completion_tokens=500,
    )


def _large_input_profile(prompt_tokens: int) -> LlmTaskCapacityProfile:
    return LlmTaskCapacityProfile(
        profile_id="prompt-a-large-input",
        estimated_prompt_tokens=prompt_tokens,
        estimated_completion_tokens=500,
    )


def _account(
    *,
    account_ref: str = "org-1",
    minute_requests: int = 2,
    minute_tokens: int = 7000,
    model_ref: str = "qwen/qwen3-32b",
    daily_requests: int = 100,
    daily_tokens: int = 50000,
) -> LlmProviderAccountCapacity:
    return LlmProviderAccountCapacity(
        provider="groq",
        account_ref=account_ref,
        model_ref=model_ref,
        remaining_minute_requests=minute_requests,
        remaining_minute_tokens=minute_tokens,
        remaining_daily_requests=daily_requests,
        remaining_daily_tokens=daily_tokens,
    )


def _work_item_row(work_item_id: str, *, ordinal: int) -> dict[str, object]:
    return {
        "work_item_id": work_item_id,
        "work_kind": _work_kind().value,
        "status": WorkItemStatus.READY.value,
        "attempt_count": 0,
        "leased_by": None,
        "lease_token": None,
        "lease_expires_at": None,
        "next_attempt_at": None,
        "last_error_kind": None,
        "created_at": _updated_at(ordinal),
        "updated_at": _updated_at(ordinal),
    }


def _connection_with_due_items(count: int) -> FakeConnection:
    connection = FakeConnection()
    for index in range(count):
        work_item_id = f"work-{index + 1}"
        connection.work_items[work_item_id] = _work_item_row(
            work_item_id,
            ordinal=index + 1,
        )
        connection.schedules[work_item_id] = {"source_unit_ref": f"unit-{index + 1}"}
    return connection


def _command(
    *,
    profile: LlmTaskCapacityProfile | None = None,
    account_capacities: tuple[LlmProviderAccountCapacity, ...] = (_account(),),
    active_model_ref: str = "qwen/qwen3-32b",
    requested_items: int = 2,
    now: datetime | None = None,
    started_at: datetime | None = None,
    dispatch_preparation_strategy: str | None = None,
) -> PrepareLlmDispatchBatchCommand:
    return PrepareLlmDispatchBatchCommand(
        work_kind=_work_kind(),
        profile=profile or _profile(),
        account_capacities=account_capacities,
        active_model_ref=active_model_ref,
        requested_items=requested_items,
        worker=_worker(),
        lease_token_prefix="lease-prefix",
        lease_expires_at=_lease_expires_at(),
        now=now or _now(),
        started_at=started_at or _started_at(),
        dispatch_preparation_strategy=dispatch_preparation_strategy,
    )


def _runner(pool: FakePool) -> PrepareLlmDispatchBatch:
    return PrepareLlmDispatchBatch(
        pool=pool,
        capacity_policy=CapacityAdmissionPolicy(),
        active_model_capacity_selector=SelectActiveLlmModelCapacity(
            projector=ProjectLlmCapacityToCapacityRuntime(),
        ),
        route_catalog=default_groq_llm_model_route_catalog(),
    )


def _as_datetime(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TypeError("expected datetime")
    return value


@pytest.mark.asyncio
async def test_commits_lease_and_attempt_start_in_one_transaction() -> None:
    connection = _connection_with_due_items(2)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(_command())

    assert len(connection.transactions) == 1
    assert connection.transactions[0].entered is True
    assert connection.transactions[0].committed is True
    assert connection.transactions[0].rolled_back is False
    assert pool.released == [connection]

    assert connection.work_items["work-1"]["status"] == "leased"
    assert connection.work_items["work-2"]["status"] == "leased"
    assert len(connection.attempts) == 2
    assert len(connection.dispatches) == 2
    assert len(result.lease_result.leased) == 2
    assert len(result.attempt_result.started_attempts) == 2


@pytest.mark.asyncio
async def test_transactional_dispatch_batch_persists_qwen_reasoning_disabled() -> None:
    connection = _connection_with_due_items(1)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(_command(requested_items=1))

    assert len(result.attempt_result.started_attempts) == 1
    dispatch = next(iter(connection.dispatches.values()))
    assert dispatch["dispatch_payload"]["llm_execution_settings"] == {
        "reasoning_enabled": False,
    }
    assert (
        dispatch["dispatch_payload"]["llm_execution_settings"]["reasoning_enabled"]
        is False
    )


@pytest.mark.asyncio
async def test_rollback_if_attempt_dispatch_insert_fails() -> None:
    connection = _connection_with_due_items(2)
    connection.fail_dispatch_insert = True
    pool = FakePool(connection=connection)

    with pytest.raises(DispatchInsertError, match="dispatch insert failed"):
        await _runner(pool).execute(_command())

    assert len(connection.transactions) == 1
    assert connection.transactions[0].rolled_back is True
    assert connection.transactions[0].exit_exc_type is DispatchInsertError
    assert pool.released == [connection]
    assert connection.work_items["work-1"]["status"] == "ready"
    assert connection.work_items["work-2"]["status"] == "ready"
    assert connection.attempts == {}
    assert connection.dispatches == {}


@pytest.mark.asyncio
async def test_capacity_exhausted_creates_no_attempts() -> None:
    connection = _connection_with_due_items(2)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(
        _command(
            account_capacities=(
                _account(
                    minute_requests=0,
                    minute_tokens=0,
                    daily_requests=0,
                    daily_tokens=0,
                ),
            ),
            requested_items=2,
        ),
    )

    assert connection.transactions[0].committed is True
    assert result.lease_result.leased == ()
    assert result.attempt_result.started_attempts == ()
    assert connection.attempts == {}
    assert connection.dispatches == {}


@pytest.mark.asyncio
async def test_no_due_work_items_creates_no_attempts() -> None:
    connection = _connection_with_due_items(0)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(_command())

    assert connection.transactions[0].committed is True
    assert result.lease_result.llm_capacity_projection.max_projected_items == 2
    assert result.lease_result.leased == ()
    assert result.attempt_result.started_attempts == ()
    assert connection.attempts == {}


def test_rejects_started_at_before_now() -> None:
    with pytest.raises(ValueError, match="started_at must be >= now"):
        _command(
            now=datetime(2026, 6, 10, 12, 1, tzinfo=timezone.utc),
            started_at=datetime(2026, 6, 10, 12, 0, tzinfo=timezone.utc),
        )


@pytest.mark.asyncio
async def test_prepare_uses_only_active_qwen_model_capacity() -> None:
    connection = _connection_with_due_items(5)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(
        _command(
            account_capacities=(
                _account(
                    account_ref="qwen_1",
                    minute_requests=10,
                    minute_tokens=7000,
                    model_ref="qwen/qwen3-32b",
                ),
                _account(
                    account_ref="qwen_2",
                    minute_requests=10,
                    minute_tokens=3500,
                    model_ref="qwen/qwen3-32b",
                ),
                _account(
                    account_ref="fallback_openai",
                    minute_requests=10,
                    minute_tokens=35000,
                    model_ref="openai/gpt-oss-120b",
                ),
            ),
            active_model_ref="qwen/qwen3-32b",
            requested_items=10,
        ),
    )

    assert result.lease_result.llm_capacity_projection.max_projected_items == 3
    assert len(result.lease_result.leased) == 3
    assert len(result.attempt_result.started_attempts) == 3
    assert len(connection.dispatches) == 3
    assert {
        dispatch["llm_allocation_payload"]["model_ref"]
        for dispatch in connection.dispatches.values()
    } == {"qwen/qwen3-32b"}


@pytest.mark.asyncio
async def test_prepare_ignores_fallback_capacities_when_qwen_is_active() -> None:
    connection = _connection_with_due_items(10)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(
        _command(
            account_capacities=(
                _account(
                    account_ref="qwen_1",
                    minute_requests=10,
                    minute_tokens=3500,
                    model_ref="qwen/qwen3-32b",
                ),
                _account(
                    account_ref="fallback_openai",
                    minute_requests=10,
                    minute_tokens=35000,
                    model_ref="openai/gpt-oss-120b",
                ),
                _account(
                    account_ref="fallback_llama",
                    minute_requests=10,
                    minute_tokens=35000,
                    model_ref="llama-3.3-70b-versatile",
                ),
            ),
            active_model_ref="qwen/qwen3-32b",
            requested_items=10,
        ),
    )

    assert result.lease_result.llm_capacity_projection.max_projected_items == 1
    assert len(result.attempt_result.started_attempts) == 1


@pytest.mark.asyncio
async def test_prepare_absent_active_model_starts_no_attempts() -> None:
    connection = _connection_with_due_items(5)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(
        _command(
            account_capacities=(
                _account(
                    account_ref="qwen_1",
                    minute_requests=10,
                    minute_tokens=35000,
                    model_ref="qwen/qwen3-32b",
                ),
            ),
            active_model_ref="openai/gpt-oss-120b",
            requested_items=10,
        ),
    )

    assert result.lease_result.llm_capacity_projection.max_projected_items == 0
    assert result.lease_result.leased == ()
    assert result.attempt_result.started_attempts == ()
    assert connection.attempts == {}
    assert connection.dispatches == {}
    assert connection.transactions[0].committed is True


@pytest.mark.asyncio
async def test_prepare_resolves_fallback_strategy_to_first_automatic_fallback_model() -> (
    None
):
    catalog = default_groq_llm_model_route_catalog()
    fallback_model_ref = catalog.automatic_fallback_model_refs()[0]
    connection = _connection_with_due_items(5)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(
        _command(
            account_capacities=(
                _account(
                    account_ref="primary",
                    model_ref=catalog.primary_model_ref(),
                    minute_requests=10,
                    minute_tokens=3500,
                ),
                _account(
                    account_ref="fallback",
                    model_ref=fallback_model_ref,
                    minute_requests=10,
                    minute_tokens=35000,
                ),
            ),
            active_model_ref=catalog.primary_model_ref(),
            dispatch_preparation_strategy="FALLBACK_MODEL_REQUIRED",
            requested_items=10,
        ),
    )

    assert len(result.attempt_result.started_attempts) == 5
    assert {
        dispatch["llm_allocation_payload"]["model_ref"]
        for dispatch in connection.dispatches.values()
    } == {fallback_model_ref}


@pytest.mark.asyncio
async def test_prepare_resolves_larger_output_strategy_to_fallback_for_now() -> None:
    catalog = default_groq_llm_model_route_catalog()
    fallback_model_ref = catalog.automatic_fallback_model_refs()[0]
    connection = _connection_with_due_items(5)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(
        _command(
            account_capacities=(
                _account(
                    account_ref="primary",
                    model_ref=catalog.primary_model_ref(),
                    minute_requests=10,
                    minute_tokens=3500,
                ),
                _account(
                    account_ref="fallback",
                    model_ref=fallback_model_ref,
                    minute_requests=10,
                    minute_tokens=35000,
                ),
            ),
            active_model_ref=catalog.primary_model_ref(),
            dispatch_preparation_strategy="LARGER_OUTPUT_LIMIT_MODEL_REQUIRED",
            requested_items=10,
        ),
    )

    assert len(result.attempt_result.started_attempts) == 5
    assert {
        dispatch["llm_allocation_payload"]["model_ref"]
        for dispatch in connection.dispatches.values()
    } == {fallback_model_ref}


@pytest.mark.asyncio
async def test_prepare_unknown_dispatch_strategy_raises_value_error() -> None:
    connection = _connection_with_due_items(1)
    pool = FakePool(connection=connection)

    with pytest.raises(ValueError, match="unknown llm dispatch preparation strategy"):
        await _runner(pool).execute(
            _command(dispatch_preparation_strategy="NO_SUCH_STRATEGY"),
        )


@pytest.mark.asyncio
async def test_prepare_uses_input_preflight_model_ref_before_leasing() -> None:
    catalog = default_groq_llm_model_route_catalog()
    fallback_model_ref = catalog.automatic_fallback_model_refs_with_larger_input_limit(
        catalog.primary_model_ref(),
    )[0]
    connection = _connection_with_due_items(2)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(
        _command(
            profile=_large_input_profile(40000),
            account_capacities=(
                _account(
                    account_ref="primary",
                    model_ref=catalog.primary_model_ref(),
                    minute_requests=10,
                    minute_tokens=500000,
                    daily_tokens=500000,
                ),
                _account(
                    account_ref="fallback",
                    model_ref=fallback_model_ref,
                    minute_requests=10,
                    minute_tokens=500000,
                    daily_tokens=500000,
                ),
            ),
            active_model_ref=catalog.primary_model_ref(),
            requested_items=2,
        ),
    )

    assert result.input_size_preflight_decision == "USE_LARGER_INPUT_MODEL"
    assert result.input_size_preflight_active_model_ref == fallback_model_ref
    assert len(result.attempt_result.started_attempts) == 2
    assert {
        dispatch["llm_allocation_payload"]["model_ref"]
        for dispatch in connection.dispatches.values()
    } == {fallback_model_ref}


@pytest.mark.asyncio
async def test_source_split_required_does_not_lease_normal_llm_work_item() -> None:
    catalog = default_groq_llm_model_route_catalog()
    connection = _connection_with_due_items(2)
    pool = FakePool(connection=connection)

    result = await _runner(pool).execute(
        _command(
            profile=_large_input_profile(200000),
            account_capacities=(
                _account(
                    account_ref="primary",
                    model_ref=catalog.primary_model_ref(),
                    minute_requests=10,
                    minute_tokens=1000000,
                    daily_tokens=1000000,
                ),
                _account(
                    account_ref="fallback",
                    model_ref=catalog.automatic_fallback_model_refs()[0],
                    minute_requests=10,
                    minute_tokens=1000000,
                    daily_tokens=1000000,
                ),
            ),
            active_model_ref=catalog.primary_model_ref(),
            requested_items=2,
        ),
    )

    assert result.source_split_required is True
    assert result.input_size_preflight_decision == "SOURCE_SPLIT_REQUIRED"
    assert result.lease_result.leased == ()
    assert result.attempt_result.started_attempts == ()
    assert connection.attempts == {}
    assert connection.dispatches == {}
    assert connection.work_items["work-1"]["status"] == "ready"
    assert connection.work_items["work-2"]["status"] == "ready"
