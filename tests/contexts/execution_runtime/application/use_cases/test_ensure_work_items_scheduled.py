from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from src.contexts.execution_runtime.application.ports.work_item_scheduling_repository_port import (
    WorkItemSchedulingRepositoryPort,
)
from src.contexts.execution_runtime.application.use_cases.ensure_work_items_scheduled import (
    EnsureWorkItemScheduledStatus,
    EnsureWorkItemsScheduled,
    EnsureWorkItemsScheduledCommand,
    WorkItemSchedulePlan,
    work_item_schedule_payload_hash,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind


@dataclass(frozen=True, slots=True)
class SavedScheduledWorkItem:
    item: WorkItem
    idempotency_key: str
    payload_hash: str
    payload: Mapping[str, object]


@dataclass(slots=True)
class FakeWorkItemSchedulingRepository:
    existing_items: dict[str, WorkItem] = field(default_factory=dict)
    schedule_payload_hashes: dict[str, str] = field(default_factory=dict)
    saved: list[SavedScheduledWorkItem] = field(default_factory=list)
    fail_on_save: bool = False

    async def get_work_item(self, work_item_id: str) -> WorkItem | None:
        return self.existing_items.get(work_item_id)

    async def get_schedule_payload_hash(self, work_item_id: str) -> str | None:
        return self.schedule_payload_hashes.get(work_item_id)

    async def save_scheduled_work_item(
        self,
        *,
        item: WorkItem,
        idempotency_key: str,
        payload_hash: str,
        payload: Mapping[str, object],
    ) -> None:
        if self.fail_on_save:
            raise RuntimeError("save failed")
        self.saved.append(
            SavedScheduledWorkItem(
                item=item,
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
                payload=payload,
            ),
        )
        self.existing_items[item.work_item_id] = item
        self.schedule_payload_hashes[item.work_item_id] = payload_hash


def _work_kind() -> WorkKind:
    return WorkKind("knowledge_workbench.claim_builder.section_extraction")


def _plan(
    *,
    work_item_id: str = "work-1",
    idempotency_key: str = "work-1",
    payload: Mapping[str, object] | None = None,
) -> WorkItemSchedulePlan:
    return WorkItemSchedulePlan(
        work_item_id=work_item_id,
        work_kind=_work_kind(),
        idempotency_key=idempotency_key,
        payload=payload
        or {
            "workflow_run_id": "run-1",
            "source_unit_ref": "source-unit-1",
            "source_unit_ordinal": 0,
        },
    )


@pytest.mark.asyncio
async def test_creates_ready_work_item_when_absent() -> None:
    plan = _plan()
    unit_of_work = FakeWorkItemSchedulingRepository()

    result = await EnsureWorkItemsScheduled(repository=unit_of_work).execute(
        EnsureWorkItemsScheduledCommand(plans=(plan,)),
    )

    assert result.created_count == 1
    assert result.already_exists_count == 0
    assert result.conflict_count == 0
    assert result.outcomes[0].status is EnsureWorkItemScheduledStatus.CREATED

    assert len(unit_of_work.saved) == 1
    saved = unit_of_work.saved[0]
    assert saved.item.work_item_id == plan.work_item_id
    assert saved.item.work_kind == plan.work_kind
    assert saved.item.status is WorkItemStatus.READY
    assert saved.idempotency_key == plan.idempotency_key
    assert saved.payload_hash == work_item_schedule_payload_hash(plan.payload)
    assert saved.payload == plan.payload


@pytest.mark.asyncio
async def test_repeated_schedule_with_same_payload_is_already_exists() -> None:
    plan = _plan()
    existing = WorkItem(work_item_id=plan.work_item_id, work_kind=plan.work_kind)
    unit_of_work = FakeWorkItemSchedulingRepository(
        existing_items={plan.work_item_id: existing},
        schedule_payload_hashes={
            plan.work_item_id: work_item_schedule_payload_hash(plan.payload),
        },
    )

    result = await EnsureWorkItemsScheduled(repository=unit_of_work).execute(
        EnsureWorkItemsScheduledCommand(plans=(plan,)),
    )

    assert result.created_count == 0
    assert result.already_exists_count == 1
    assert result.conflict_count == 0
    assert result.outcomes[0].status is (EnsureWorkItemScheduledStatus.ALREADY_EXISTS)
    assert result.outcomes[0].existing_work_item == existing
    assert unit_of_work.saved == []


@pytest.mark.asyncio
async def test_existing_with_different_payload_hash_is_conflict() -> None:
    plan = _plan(payload={"source_unit_ref": "new"})
    existing = WorkItem(work_item_id=plan.work_item_id, work_kind=plan.work_kind)
    unit_of_work = FakeWorkItemSchedulingRepository(
        existing_items={plan.work_item_id: existing},
        schedule_payload_hashes={plan.work_item_id: "different-hash"},
    )

    result = await EnsureWorkItemsScheduled(repository=unit_of_work).execute(
        EnsureWorkItemsScheduledCommand(plans=(plan,)),
    )

    assert result.created_count == 0
    assert result.already_exists_count == 0
    assert result.conflict_count == 1
    assert result.outcomes[0].status is EnsureWorkItemScheduledStatus.CONFLICT
    assert result.outcomes[0].existing_work_item == existing
    assert unit_of_work.saved == []


@pytest.mark.asyncio
async def test_mixed_created_already_exists_and_conflict_counts() -> None:
    created = _plan(work_item_id="work-created", idempotency_key="work-created")
    already_exists = _plan(
        work_item_id="work-existing",
        idempotency_key="work-existing",
        payload={"stable": "payload"},
    )
    conflict = _plan(
        work_item_id="work-conflict",
        idempotency_key="work-conflict",
        payload={"new": "payload"},
    )
    existing_same = WorkItem(
        work_item_id=already_exists.work_item_id,
        work_kind=already_exists.work_kind,
    )
    existing_conflict = WorkItem(
        work_item_id=conflict.work_item_id,
        work_kind=conflict.work_kind,
    )
    unit_of_work = FakeWorkItemSchedulingRepository(
        existing_items={
            already_exists.work_item_id: existing_same,
            conflict.work_item_id: existing_conflict,
        },
        schedule_payload_hashes={
            already_exists.work_item_id: work_item_schedule_payload_hash(
                already_exists.payload,
            ),
            conflict.work_item_id: "old-hash",
        },
    )

    result = await EnsureWorkItemsScheduled(repository=unit_of_work).execute(
        EnsureWorkItemsScheduledCommand(plans=(created, already_exists, conflict)),
    )

    assert result.created_count == 1
    assert result.already_exists_count == 1
    assert result.conflict_count == 1
    assert [outcome.status for outcome in result.outcomes] == [
        EnsureWorkItemScheduledStatus.CREATED,
        EnsureWorkItemScheduledStatus.ALREADY_EXISTS,
        EnsureWorkItemScheduledStatus.CONFLICT,
    ]


@pytest.mark.asyncio
async def test_duplicate_work_item_id_in_command_is_rejected() -> None:
    with pytest.raises(ValueError, match="work_item_id must be unique"):
        EnsureWorkItemsScheduledCommand(
            plans=(
                _plan(work_item_id="duplicate"),
                _plan(work_item_id="duplicate"),
            ),
        )


@pytest.mark.asyncio
async def test_save_failure_re_raises_without_transaction_handling() -> None:
    unit_of_work = FakeWorkItemSchedulingRepository(fail_on_save=True)

    with pytest.raises(RuntimeError, match="save failed"):
        await EnsureWorkItemsScheduled(repository=unit_of_work).execute(
            EnsureWorkItemsScheduledCommand(plans=(_plan(),)),
        )

    assert unit_of_work.saved == []


@pytest.mark.asyncio
async def test_payload_hash_is_deterministic() -> None:
    left = {"b": 2, "a": 1}
    right = {"a": 1, "b": 2}

    assert work_item_schedule_payload_hash(left) == work_item_schedule_payload_hash(
        right,
    )


@pytest.mark.asyncio
async def test_use_case_accepts_scheduling_repository_port() -> None:
    unit_of_work: WorkItemSchedulingRepositoryPort = FakeWorkItemSchedulingRepository()

    result = await EnsureWorkItemsScheduled(repository=unit_of_work).execute(
        EnsureWorkItemsScheduledCommand(plans=()),
    )

    assert result.outcomes == ()


@pytest.mark.asyncio
async def test_ensure_work_items_scheduled_source_guard() -> None:
    use_case = Path(
        "src/contexts/execution_runtime/application/use_cases/"
        "ensure_work_items_scheduled.py",
    ).read_text(encoding="utf-8")
    port = Path(
        "src/contexts/execution_runtime/application/ports/"
        "work_item_scheduling_repository_port.py",
    ).read_text(encoding="utf-8")
    combined = use_case + port

    required_markers = (
        "EnsureWorkItemsScheduled",
        "EnsureWorkItemsScheduledCommand",
        "WorkItemSchedulePlan",
        "EnsureWorkItemScheduledStatus",
        "EnsureWorkItemScheduledOutcome",
        "work_item_schedule_payload_hash",
        "WorkItemSchedulingRepositoryPort",
        "save_scheduled_work_item",
        "get_schedule_payload_hash",
    )
    forbidden_markers = (
        "knowledge_workbench",
        "capacity_runtime",
        "llm_runtime",
        "artifact_runtime",
        "Postgres",
        "asyncpg",
        "queue",
        "worker_loop",
        "JobDispatcher",
        "lease",
        "Groq",
        "qwen",
    )

    for marker in required_markers:
        assert marker in combined

    for marker in forbidden_markers:
        assert marker not in combined


def test_ensure_work_items_scheduled_does_not_commit_or_rollback() -> None:
    source = Path(
        "src/contexts/execution_runtime/application/use_cases/"
        "ensure_work_items_scheduled.py",
    ).read_text(encoding="utf-8")

    assert ".commit(" not in source
    assert ".rollback(" not in source
    assert "async def commit" not in source
    assert "async def rollback" not in source
