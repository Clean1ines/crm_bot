from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol


class ClaimExtractionWorkItemCreatorPort(Protocol):
    def execute(self, command: object) -> object: ...


class ClaimExtractionStageWorkItemIndexPort(Protocol):
    def save_stage_work_item(self, *, workflow_run_id: str, stage_run_id: str, source_unit: object, work_item: object) -> None: