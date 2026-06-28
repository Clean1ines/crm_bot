from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


class CapacityAdmissionProjectionLifecycleSynchronizerPort(Protocol):
    async def execute(self, *args: Any, **kwargs: Any) -> object: ...

    async def synchronize(self, *args: Any, **kwargs: Any) -> object: ...


@dataclass(frozen=True, slots=True)
class CapacityAdmissionProjectionLifecycleUpdate:
    work_item_id: str
    status: str
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class SyncCapacityAdmissionProjectionLifecycleCommand:
    updates: tuple[CapacityAdmissionProjectionLifecycleUpdate, ...]


class SyncCapacityAdmissionProjectionLifecycle:
    def __init__(
        self,
        synchronizer: CapacityAdmissionProjectionLifecycleSynchronizerPort,
    ) -> None:
        self.synchronizer = synchronizer

    async def execute(
        self,
        command: SyncCapacityAdmissionProjectionLifecycleCommand,
    ) -> None:
        return None
