from __future__ import annotations

from dataclasses import dataclass

from src.contexts.llm_runtime.application.capacity.project_llm_capacity_to_capacity_runtime import (
    LlmCapacityProjectionCommand,
    LlmCapacityProjectionResult,
    ProjectLlmCapacityToCapacityRuntime,
    zero_llm_capacity_projection,
)
from src.contexts.llm_runtime.domain.capacity.llm_provider_account_capacity import (
    LlmProviderAccountCapacity,
)
from src.contexts.llm_runtime.domain.capacity.llm_task_capacity_profile import (
    LlmTaskCapacityProfile,
)


@dataclass(frozen=True, slots=True)
class SelectActiveLlmModelCapacityCommand:
    profile: LlmTaskCapacityProfile
    account_capacities: tuple[LlmProviderAccountCapacity, ...]
    active_model_ref: str
    requested_items: int

    def __post_init__(self) -> None:
        if not isinstance(self.profile, LlmTaskCapacityProfile):
            raise TypeError("profile must be LlmTaskCapacityProfile")
        if not isinstance(self.account_capacities, tuple):
            raise TypeError("account_capacities must be tuple")
        if not self.account_capacities:
            raise ValueError("account_capacities must be non-empty")
        for account in self.account_capacities:
            if not isinstance(account, LlmProviderAccountCapacity):
                raise TypeError(
                    "account_capacities must contain LlmProviderAccountCapacity",
                )
        _require_non_empty_text(self.active_model_ref, field_name="active_model_ref")
        if not isinstance(self.requested_items, int):
            raise TypeError("requested_items must be int")
        if self.requested_items <= 0:
            raise ValueError("requested_items must be > 0")


@dataclass(frozen=True, slots=True)
class SelectActiveLlmModelCapacityResult:
    active_model_ref: str
    selected_accounts: tuple[LlmProviderAccountCapacity, ...]
    projection: LlmCapacityProjectionResult

    def __post_init__(self) -> None:
        _require_non_empty_text(self.active_model_ref, field_name="active_model_ref")
        if not isinstance(self.selected_accounts, tuple):
            raise TypeError("selected_accounts must be tuple")
        for account in self.selected_accounts:
            if not isinstance(account, LlmProviderAccountCapacity):
                raise TypeError(
                    "selected_accounts must contain LlmProviderAccountCapacity"
                )
            if account.model_ref != self.active_model_ref:
                raise ValueError("selected_accounts must match active_model_ref")
        if not isinstance(self.projection, LlmCapacityProjectionResult):
            raise TypeError("projection must be LlmCapacityProjectionResult")


@dataclass(frozen=True, slots=True)
class SelectActiveLlmModelCapacity:
    projector: ProjectLlmCapacityToCapacityRuntime

    def execute(
        self,
        command: SelectActiveLlmModelCapacityCommand,
    ) -> SelectActiveLlmModelCapacityResult:
        selected_accounts = tuple(
            account
            for account in command.account_capacities
            if account.model_ref == command.active_model_ref
        )
        if selected_accounts:
            projection = self.projector.execute(
                LlmCapacityProjectionCommand(
                    profile=command.profile,
                    accounts=selected_accounts,
                    requested_items=command.requested_items,
                ),
            )
        else:
            projection = zero_llm_capacity_projection(
                requested_items=command.requested_items,
            )

        return SelectActiveLlmModelCapacityResult(
            active_model_ref=command.active_model_ref,
            selected_accounts=selected_accounts,
            projection=projection,
        )


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
