from __future__ import annotations

from dataclasses import dataclass

from src.contexts.execution_runtime.application.ports.work_item_split_supersede_repository_port import (
    WorkItemSplitSupersedeRepositoryPort,
)
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    WorkItemStateMachine,
)


@dataclass(frozen=True, slots=True)
class SupersedeWaitingWorkItemsForSplitCommand:
    work_item_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty_text_tuple(
            self.work_item_ids,
            field_name="work_item_ids",
        )


@dataclass(frozen=True, slots=True)
class SupersedeWaitingWorkItemsForSplitResult:
    superseded_work_item_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        _require_non_empty_text_tuple(
            self.superseded_work_item_ids,
            field_name="superseded_work_item_ids",
        )


class SupersedeWaitingWorkItemsForSplit:
    def __init__(
        self,
        *,
        repository: WorkItemSplitSupersedeRepositoryPort,
    ) -> None:
        self._repository = repository

    async def execute(
        self,
        command: SupersedeWaitingWorkItemsForSplitCommand,
    ) -> SupersedeWaitingWorkItemsForSplitResult:
        superseded_work_item_ids: list[str] = []

        for work_item_id in command.work_item_ids:
            item = await self._repository.load_work_item(work_item_id)
            if item is None:
                raise ValueError(f"work item not found: {work_item_id}")

            superseded_item = WorkItemStateMachine.mark_split_superseded_waiting(item)
            await self._repository.save_work_item(superseded_item)
            superseded_work_item_ids.append(superseded_item.work_item_id)

        return SupersedeWaitingWorkItemsForSplitResult(
            superseded_work_item_ids=tuple(superseded_work_item_ids),
        )


def _require_non_empty_text_tuple(
    value: tuple[str, ...],
    *,
    field_name: str,
) -> None:
    if not isinstance(value, tuple):
        raise TypeError(f"{field_name} must be tuple")
    if not value:
        raise ValueError(f"{field_name} must be non-empty")
    for item in value:
        if not isinstance(item, str):
            raise TypeError(f"{field_name} must contain str")
        if not item.strip():
            raise ValueError(f"{field_name} must contain non-empty text")
