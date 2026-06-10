from dataclasses import dataclass
from enum import StrEnum


class CapacityResourceKind(StrEnum):
    WORKER_SLOT = "WORKER_SLOT"
    CPU_SLOT = "CPU_SLOT"
    MEMORY_MB = "MEMORY_MB"
    DB_CONNECTION = "DB_CONNECTION"
    FILESYSTEM_IO = "FILESYSTEM_IO"
    LOCAL_GPU_LANE = "LOCAL_GPU_LANE"
    EXTERNAL_IO = "EXTERNAL_IO"


class CapacityWorkClass(StrEnum):
    LLM_BOUND = "LLM_BOUND"
    CPU_BOUND = "CPU_BOUND"
    EMBEDDING_BOUND = "EMBEDDING_BOUND"
    PARSING_BOUND = "PARSING_BOUND"
    IO_BOUND = "IO_BOUND"


class CapacityDecisionStatus(StrEnum):
    ALLOW = "ALLOW"
    THROTTLE = "THROTTLE"
    REJECT = "REJECT"


@dataclass(frozen=True, slots=True)
class CapacityNeed:
    resource_kind: CapacityResourceKind
    amount: int

    def __post_init__(self) -> None:
        _require_resource_kind(self.resource_kind)
        if not isinstance(self.amount, int):
            raise TypeError("amount must be int")
        if self.amount <= 0:
            raise ValueError("amount must be > 0")


@dataclass(frozen=True, slots=True)
class CapacityAvailability:
    resource_kind: CapacityResourceKind
    available_amount: int

    def __post_init__(self) -> None:
        _require_resource_kind(self.resource_kind)
        if not isinstance(self.available_amount, int):
            raise TypeError("available_amount must be int")
        if self.available_amount < 0:
            raise ValueError("available_amount must be >= 0")


@dataclass(frozen=True, slots=True)
class CapacityRequest:
    work_class: CapacityWorkClass
    needs: tuple[CapacityNeed, ...]

    def __post_init__(self) -> None:
        _require_work_class(self.work_class)
        if not isinstance(self.needs, tuple):
            raise TypeError("needs must be tuple")
        if not self.needs:
            raise ValueError("needs must be non-empty")
        for need in self.needs:
            if not isinstance(need, CapacityNeed):
                raise TypeError("needs must contain CapacityNeed")
        _require_unique_resource_kinds(
            tuple(need.resource_kind for need in self.needs),
            field_name="needs",
        )


@dataclass(frozen=True, slots=True)
class CapacitySnapshot:
    availability: tuple[CapacityAvailability, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.availability, tuple):
            raise TypeError("availability must be tuple")
        for item in self.availability:
            if not isinstance(item, CapacityAvailability):
                raise TypeError("availability must contain CapacityAvailability")
        _require_unique_resource_kinds(
            tuple(item.resource_kind for item in self.availability),
            field_name="availability",
        )

    def available_for(self, resource_kind: CapacityResourceKind) -> int:
        _require_resource_kind(resource_kind)
        for item in self.availability:
            if item.resource_kind is resource_kind:
                return item.available_amount
        return 0


@dataclass(frozen=True, slots=True)
class CapacityDecision:
    status: CapacityDecisionStatus
    work_class: CapacityWorkClass
    blocking_resources: tuple[CapacityResourceKind, ...] = ()
    reason: str = ""

    def __post_init__(self) -> None:
        if not isinstance(self.status, CapacityDecisionStatus):
            raise TypeError("status must be CapacityDecisionStatus")
        _require_work_class(self.work_class)
        if not isinstance(self.blocking_resources, tuple):
            raise TypeError("blocking_resources must be tuple")
        for resource_kind in self.blocking_resources:
            _require_resource_kind(resource_kind)
        if not isinstance(self.reason, str) or not self.reason.strip():
            raise ValueError("reason must be non-empty")

        if self.status is CapacityDecisionStatus.ALLOW:
            if self.blocking_resources:
                raise ValueError("ALLOW decision must not have blocking_resources")
            return

        if not self.blocking_resources:
            raise ValueError("THROTTLE/REJECT decision must have blocking_resources")

    def is_allowed(self) -> bool:
        return self.status is CapacityDecisionStatus.ALLOW


def _require_resource_kind(value: CapacityResourceKind) -> None:
    if not isinstance(value, CapacityResourceKind):
        raise TypeError("resource_kind must be CapacityResourceKind")


def _require_work_class(value: CapacityWorkClass) -> None:
    if not isinstance(value, CapacityWorkClass):
        raise TypeError("work_class must be CapacityWorkClass")


def _require_unique_resource_kinds(
    resource_kinds: tuple[CapacityResourceKind, ...],
    *,
    field_name: str,
) -> None:
    seen: set[CapacityResourceKind] = set()
    for resource_kind in resource_kinds:
        _require_resource_kind(resource_kind)
        if resource_kind in seen:
            raise ValueError(f"{field_name} must not contain duplicate resource_kind")
        seen.add(resource_kind)
