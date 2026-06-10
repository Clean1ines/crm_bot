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
class LlmCapacityAllocationSlot:
    provider: str
    account_ref: str
    model_ref: str
    slot_index: int

    def __post_init__(self) -> None:
        _require_non_empty_text(self.provider, field_name="provider")
        _require_non_empty_text(self.account_ref, field_name="account_ref")
        _require_non_empty_text(self.model_ref, field_name="model_ref")
        if not isinstance(self.slot_index, int):
            raise TypeError("slot_index must be int")
        if self.slot_index < 0:
            raise ValueError("slot_index must be >= 0")

    def to_payload(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "account_ref": self.account_ref,
            "model_ref": self.model_ref,
            "slot_index": self.slot_index,
        }


@dataclass(frozen=True, slots=True)
class LlmCapacityProjectionResult:
    capacity_needs: tuple[CapacityNeed, ...]
    capacity_snapshot: CapacitySnapshot
    requested_items: int
    max_projected_items: int
    allocations: tuple[LlmCapacityAllocationSlot, ...]

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
        if not isinstance(self.allocations, tuple):
            raise TypeError("allocations must be tuple")
        for allocation in self.allocations:
            if not isinstance(allocation, LlmCapacityAllocationSlot):
                raise TypeError("allocations must contain LlmCapacityAllocationSlot")
        if len(self.allocations) != self.max_projected_items:
            raise ValueError("allocations length must equal max_projected_items")

        expected_slot_indexes = tuple(range(self.max_projected_items))
        actual_slot_indexes = tuple(
            allocation.slot_index for allocation in self.allocations
        )
        if actual_slot_indexes != expected_slot_indexes:
            raise ValueError("allocation slot_index values must be contiguous")


class ProjectLlmCapacityToCapacityRuntime:
    def execute(
        self,
        command: LlmCapacityProjectionCommand,
    ) -> LlmCapacityProjectionResult:
        projected_items = sum(
            account.max_items_for(command.profile) for account in command.accounts
        )
        max_projected_items = min(command.requested_items, projected_items)
        allocations = _build_allocation_slots(
            accounts=command.accounts,
            profile=command.profile,
            max_projected_items=max_projected_items,
        )
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
            allocations=allocations,
        )


def _build_allocation_slots(
    *,
    accounts: tuple[LlmProviderAccountCapacity, ...],
    profile: LlmTaskCapacityProfile,
    max_projected_items: int,
) -> tuple[LlmCapacityAllocationSlot, ...]:
    allocations: list[LlmCapacityAllocationSlot] = []
    for account in accounts:
        account_capacity = account.max_items_for(profile)
        for _ in range(account_capacity):
            if len(allocations) >= max_projected_items:
                break
            allocations.append(
                LlmCapacityAllocationSlot(
                    provider=account.provider,
                    account_ref=account.account_ref,
                    model_ref=account.model_ref,
                    slot_index=len(allocations),
                ),
            )
        if len(allocations) >= max_projected_items:
            break
    return tuple(allocations)


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
