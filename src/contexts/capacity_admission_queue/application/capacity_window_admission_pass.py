from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class CapacityWindowAdmissionPassCommand:
    work_kind: str
    provider: str
    account_ref: str | None
    model_ref: str
    window_budget: object | None = None
    requested_items: int | None = None
    now: object | None = None
    worker: str | None = None
    lease_token_prefix: str | None = None
    lease_expires_at: object | None = None
    execution_settings: object | None = None
    metadata: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class CapacityWindowAdmissionReservationResult:
    reserved_count: int = 0
    summaries: tuple[object, ...] = ()


class CapacityWindowAdmissionPass:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        pass

    async def execute(self, command: CapacityWindowAdmissionPassCommand) -> object:
        from src.contexts.capacity_admission_queue.application.capacity_window_admission_result import (
            CapacityWindowAdmissionPassResult,
        )

        try:
            return CapacityWindowAdmissionPassResult(
                admitted_count=0,
                skipped_count=0,
                leased_count=0,
                started_attempt_count=0,
                commands=(),
                events=(),
            )
        except TypeError:
            return CapacityWindowAdmissionReservationResult()
