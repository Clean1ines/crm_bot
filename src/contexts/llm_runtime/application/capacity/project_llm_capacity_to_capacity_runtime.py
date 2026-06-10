from __future__ import annotations

from dataclasses import dataclass

from src.contexts.capacity_runtime.domain.capacity_decision import (
    CapacityAvailability,
    CapacityNeed,
    CapacityResourceKind,
    CapacitySnapshot,
)
from src.contexts.llm_runtime.domain.capacity.llm_provider_account_capacity import (
    LlmProviderAccountCapacity,
)
from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)


@dataclass(frozen=True, slots=True)
class LlmCapacityProjectionCommand:
    profile: LlmTaskCapacityProfile
    accounts: tuple[LlmProviderAccountCapacity, ...]
    requested_items: int

    def __post_init__(self) -> None:
        if not isinstance(self.profile, LlmTaskCapacityProfile):
            raise TypeError("profile must be LlmTaskCapacityProfile")
        if not isinstance(self.accounts, tuple):
            raise TypeError("accounts must be tuple")
        if not self.accounts:
            raise ValueError("accounts must be non-empty")
        for account in self.accounts:
            if not isinstance(account, LlmProviderAccountCapacity):
                raise TypeError("accounts must contain LlmProviderAccountCapacity")
        if not isinstance(self.requested_items, int):
            raise TypeError("requested_items must be int")
        if self.requested_items <= 0:
            raise ValueError("requested_items must be > 0")


@dataclass(frozen=True, slots=True)
class LlmCapacityProjectionResult:
    capacity_needs: tuple[CapacityNeed, ...]
    capacity_snapshot: CapacitySnapshot
    requested_items: int
    max_projected_items: int

    def __post_init__(self) -> None:
        if not isinstance(self.capacity_needs, tuple):
            raise TypeError("capacity_needs must be tuple")
        if not self.capacity_needs:
            raise ValueError("capacity_needs must be non-empty")
        for need in self.capacity_needs:
            if not isinstance(need, CapacityNeed):
                raise TypeError("capacity_needs must contain CapacityNeed")
        if not isinstance(self.capacity_snapshot, CapacitySnapshot):
            raise TypeError("capacity_snapshot must be CapacitySnapshot")
        if not isinstance(self.requested_items, int):
            raise TypeError("requested_items must be int")
        if self.requested_items <= 0:
            raise ValueError("requested_items must be > 0")
        if not isinstance(self.max_projected_items, int):
            raise TypeError("max_projected_items must be int")
        if self.max_projected_items < 0:
            raise ValueError("max_projected_items must be >= 0")
        if self.max_projected_items > self.requested_items:
            raise ValueError("max_projected_items must be <= requested_items")


class ProjectLlmCapacityToCapacityRuntime:
    def execute(
        self,
        command: LlmCapacityProjectionCommand,
    ) -> LlmCapacityProjectionResult:
        projected_items = sum(
            account.max_items_for(command.profile) for account in command.accounts
        )
        max_projected_items = min(command.requested_items, projected_items)
        return LlmCapacityProjectionResult(
            capacity_needs=(
                CapacityNeed(
                    resource_kind=CapacityResourceKind.EXTERNAL_IO,
                    amount=1,
                ),
            ),
            capacity_snapshot=CapacitySnapshot(
                availability=(
                    CapacityAvailability(
                        resource_kind=CapacityResourceKind.EXTERNAL_IO,
                        available_amount=max_projected_items,
                    ),
                ),
            ),
            requested_items=command.requested_items,
            max_projected_items=max_projected_items,
        )
