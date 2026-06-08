from __future__ import annotations

from dataclasses import dataclass

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)


CLAIM_EXTRACTION_WORK_KIND = WorkKind("knowledge_workbench.claim_extraction")


@dataclass(frozen=True, slots=True)
class CreateExtractionWorkItemsCommand:
    source_units: tuple[SourceUnit, ...]
    prompt_id: str

    def __post_init__(self) -> None:
        if not self.source_units:
            raise ValueError("source_units must be non-empty")
        if not self.prompt_id or not self.prompt_id.strip():
            raise ValueError("prompt_id must be non-empty")


@dataclass(frozen=True, slots=True)
class CreateExtractionWorkItemsResult:
    work_items: tuple[WorkItem, ...]


class CreateExtractionWorkItems:
    def execute(
        self,
        command: CreateExtractionWorkItemsCommand,
    ) -> CreateExtractionWorkItemsResult:
        work_items = tuple(
            WorkItem(
                work_item_id=self._work_item_id(
                    prompt_id=command.prompt_id,
                    source_unit=source_unit,
                ),
                work_kind=CLAIM_EXTRACTION_WORK_KIND,
            )
            for source_unit in command.source_units
        )

        return CreateExtractionWorkItemsResult(work_items=work_items)

    def _work_item_id(self, *, prompt_id: str, source_unit: SourceUnit) -> str:
        return f"claim-extraction:{prompt_id}:{source_unit.unit_ref.value}"
