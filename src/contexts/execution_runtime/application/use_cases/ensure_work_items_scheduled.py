from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum

from src.contexts.execution_runtime.application.ports.work_item_scheduling_repository_port import (
    WorkItemSchedulingRepositoryPort,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind


@dataclass(frozen=True, slots=True)
class WorkItemSchedulePlan:
    work_item_id: str
    work_kind: WorkKind
    idempotency_key: str
    payload: Mapping[str, object]

    def __post_init__(self) -> None:
        _require_non_empty_text(self.work_item_id, field_name="work_item_id")
        if not isinstance(self.work_kind, WorkKind):
            raise TypeError("work_kind must be WorkKind")
        _require_non_empty_text(
            self.idempotency_key,
            field_name="idempotency_key",
        )
        if not isinstance(self.payload, Mapping):
            raise TypeError("payload must be Mapping")


class EnsureWorkItemScheduledStatus(StrEnum):
    CREATED = "created"
    ALREADY_EXISTS = "already_exists"
    CONFLICT = "conflict"


@dataclass(frozen=True, slots=True)
class EnsureWorkItemScheduledOutcome:
    plan: WorkItemSchedulePlan
    status: EnsureWorkItemScheduledStatus
    existing_work_item: WorkItem | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.plan, WorkItemSchedulePlan):
            raise TypeError("plan must be WorkItemSchedulePlan")
        if not isinstance(self.status, EnsureWorkItemScheduledStatus):
            raise TypeError("status must be EnsureWorkItemScheduledStatus")
        if self.existing_work_item is not None and not isinstance(
            self.existing_work_item,
            WorkItem,
        ):
            raise TypeError("existing_work_item must be WorkItem or None")


@dataclass(frozen=True, slots=True)
class EnsureWorkItemsScheduledResult:
    outcomes: tuple[EnsureWorkItemScheduledOutcome, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.outcomes, tuple):
            raise TypeError("outcomes must be tuple")
        for outcome in self.outcomes:
            if not isinstance(outcome, EnsureWorkItemScheduledOutcome):
                raise TypeError(
                    "outcomes must contain only EnsureWorkItemScheduledOutcome",
                )

    @property
    def created_count(self) -> int:
        return self._count(EnsureWorkItemScheduledStatus.CREATED)

    @property
    def already_exists_count(self) -> int:
        return self._count(EnsureWorkItemScheduledStatus.ALREADY_EXISTS)

    @property
    def conflict_count(self) -> int:
        return self._count(EnsureWorkItemScheduledStatus.CONFLICT)

    def _count(self, status: EnsureWorkItemScheduledStatus) -> int:
        return sum(1 for outcome in self.outcomes if outcome.status is status)


@dataclass(frozen=True, slots=True)
class EnsureWorkItemsScheduledCommand:
    plans: tuple[WorkItemSchedulePlan, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.plans, tuple):
            raise TypeError("plans must be tuple")

        seen_work_item_ids: set[str] = set()
        for plan in self.plans:
            if not isinstance(plan, WorkItemSchedulePlan):
                raise TypeError("plans must contain only WorkItemSchedulePlan")
            if plan.work_item_id in seen_work_item_ids:
                raise ValueError("work_item_id must be unique")
            seen_work_item_ids.add(plan.work_item_id)


@dataclass(frozen=True, slots=True)
class EnsureWorkItemsScheduled:
    repository: WorkItemSchedulingRepositoryPort

    async def execute(
        self,
        command: EnsureWorkItemsScheduledCommand,
    ) -> EnsureWorkItemsScheduledResult:
        outcomes: list[EnsureWorkItemScheduledOutcome] = []

        for plan in command.plans:
            outcomes.append(await self._ensure_plan(plan))

        return EnsureWorkItemsScheduledResult(outcomes=tuple(outcomes))

    async def _ensure_plan(
        self,
        plan: WorkItemSchedulePlan,
    ) -> EnsureWorkItemScheduledOutcome:
        existing = await self.repository.get_work_item(plan.work_item_id)
        payload_hash = work_item_schedule_payload_hash(plan.payload)

        if existing is None:
            item = WorkItem(
                work_item_id=plan.work_item_id,
                work_kind=plan.work_kind,
            )
            await self.repository.save_scheduled_work_item(
                item=item,
                idempotency_key=plan.idempotency_key,
                payload_hash=payload_hash,
                payload=plan.payload,
            )
            return EnsureWorkItemScheduledOutcome(
                plan=plan,
                status=EnsureWorkItemScheduledStatus.CREATED,
            )

        existing_payload_hash = await self.repository.get_schedule_payload_hash(
            plan.work_item_id,
        )
        if existing_payload_hash == payload_hash:
            return EnsureWorkItemScheduledOutcome(
                plan=plan,
                status=EnsureWorkItemScheduledStatus.ALREADY_EXISTS,
                existing_work_item=existing,
            )

        return EnsureWorkItemScheduledOutcome(
            plan=plan,
            status=EnsureWorkItemScheduledStatus.CONFLICT,
            existing_work_item=existing,
        )


def work_item_schedule_payload_hash(payload: Mapping[str, object]) -> str:
    payload_json = json.dumps(
        payload,
        default=str,
        separators=(",", ":"),
        sort_keys=True,
    )
    return hashlib.sha256(payload_json.encode("utf-8")).hexdigest()


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
