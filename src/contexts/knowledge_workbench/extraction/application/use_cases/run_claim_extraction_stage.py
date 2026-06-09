from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from src.contexts.execution_runtime.application.ports.work_item_unit_of_work_port import WorkItemUnitOfWorkPort
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.work_item_status import WorkItemStatus
from src.contexts.knowledge_workbench.extraction.application.use_cases.create_extraction_work_items import CreateExtractionWorkItems, CreateExtractionWorkItemsCommand
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import SourceUnit


class ClaimExtractionWorkItemCreatorPort(Protocol):
    def execute(self, command: CreateExtractionWorkItemsCommand) -> object: ...


class ClaimExtractionStageWorkItemIndexPort(Protocol):
    def save_stage_work_item(self, *, workflow_run_id: str, stage_run_id: str, source_unit: SourceUnit, work_item: WorkItem) -> None: ...


class ClaimExtractionStageStatus(StrEnum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    WAITING = "waiting"
    USER_ACTION_REQUIRED = "user_action_required"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass