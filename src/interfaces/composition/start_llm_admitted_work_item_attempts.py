from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime

from src.contexts.execution_runtime.application.ports.work_item_attempt_dispatch_repository_port import (
    WorkItemAttemptDispatchRecord,
    WorkItemAttemptDispatchRepositoryPort,
)
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.interfaces.composition.lease_llm_admitted_work_items import (
    LlmAdmittedLeasedWorkItem,
)


@dataclass(frozen=True, slots=True)
class StartedLlmAdmittedAttempt:
    attempt_id: str
    work_item_id: str
    attempt_number: int
    dispatch_payload: Mapping[str, object]

    def __post_init__(self) -> None:
        _require_non_empty_text(self.attempt_id, field_name="attempt_id")
        _require_non_empty_text(self.work_item_id, field_name="work_item_id")
        if not isinstance(self.attempt_number, int):
            raise TypeError("attempt_number must be int")
        if self.attempt_number <= 0:
            raise ValueError("attempt_number must be > 0")
        if not isinstance(self.dispatch_payload, Mapping):
            raise TypeError("dispatch_payload must be Mapping")


@dataclass(frozen=True, slots=True)
class StartLlmAdmittedWorkItemAttemptsCommand:
    leased_items: tuple[LlmAdmittedLeasedWorkItem, ...]
    started_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.leased_items, tuple):
            raise TypeError("leased_items must be tuple")
        for item in self.leased_items:
            if not isinstance(item, LlmAdmittedLeasedWorkItem):
                raise TypeError("leased_items must contain LlmAdmittedLeasedWorkItem")
        _require_timezone_aware(self.started_at, field_name="started_at")


@dataclass(frozen=True, slots=True)
class StartLlmAdmittedWorkItemAttemptsResult:
    started_attempts: tuple[StartedLlmAdmittedAttempt, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.started_attempts, tuple):
            raise TypeError("started_attempts must be tuple")
        for attempt in self.started_attempts:
            if not isinstance(attempt, StartedLlmAdmittedAttempt):
                raise TypeError(
                    "started_attempts must contain StartedLlmAdmittedAttempt"
                )


@dataclass(frozen=True, slots=True)
class StartLlmAdmittedWorkItemAttempts:
    repository: WorkItemAttemptDispatchRepositoryPort

    async def execute(
        self,
        command: StartLlmAdmittedWorkItemAttemptsCommand,
    ) -> StartLlmAdmittedWorkItemAttemptsResult:
        started_attempts: list[StartedLlmAdmittedAttempt] = []
        for item in command.leased_items:
            record = _build_dispatch_record(
                item=item,
                started_at=command.started_at,
            )
            await self.repository.save_started_dispatch_attempt(record)
            started_attempts.append(
                StartedLlmAdmittedAttempt(
                    attempt_id=record.attempt_id,
                    work_item_id=record.work_item_id,
                    attempt_number=record.attempt_number,
                    dispatch_payload=record.dispatch_payload,
                ),
            )

        return StartLlmAdmittedWorkItemAttemptsResult(
            started_attempts=tuple(started_attempts),
        )


def _build_dispatch_record(
    *,
    item: LlmAdmittedLeasedWorkItem,
    started_at: datetime,
) -> WorkItemAttemptDispatchRecord:
    work_item = item.leased.work_item
    if work_item.status is not WorkItemStatus.LEASED:
        raise ValueError("work_item must be leased")
    if work_item.lease_token is None:
        raise ValueError("leased work_item must have lease_token")
    if work_item.leased_by is None:
        raise ValueError("leased work_item must have leased_by")
    if work_item.attempt_count <= 0:
        raise ValueError("leased work_item attempt_count must be > 0")

    attempt_id = work_item.lease_token.value
    llm_allocation_payload = item.allocation.to_payload()
    dispatch_payload = item.to_dispatch_payload()

    return WorkItemAttemptDispatchRecord(
        attempt_id=attempt_id,
        work_item_id=work_item.work_item_id,
        attempt_number=work_item.attempt_count,
        lease_token=work_item.lease_token.value,
        worker_ref=work_item.leased_by.value,
        schedule_payload=item.admitted_schedule_payload(),
        llm_allocation_payload=llm_allocation_payload,
        dispatch_payload=dispatch_payload,
        started_at=started_at,
    )


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_timezone_aware(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
