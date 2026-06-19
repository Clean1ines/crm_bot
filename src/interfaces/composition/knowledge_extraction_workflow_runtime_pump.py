from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import structlog


LOGGER = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DueKnowledgeExtractionWorkflow:
    project_id: str
    workflow_run_id: str

    def __post_init__(self) -> None:
        _require_non_empty_text(self.project_id, field_name="project_id")
        _require_non_empty_text(
            self.workflow_run_id,
            field_name="workflow_run_id",
        )


class DueKnowledgeExtractionWorkflowReaderPort(Protocol):
    async def list_due_workflows(
        self,
        *,
        limit: int,
    ) -> tuple[DueKnowledgeExtractionWorkflow, ...]: ...


class KnowledgeExtractionWorkflowRunnerPort(Protocol):
    async def run(
        self,
        *,
        project_id: str,
        workflow_run_id: str,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class KnowledgeExtractionWorkflowRuntimePumpResult:
    inspected_count: int
    succeeded_count: int
    failed_count: int

    def __post_init__(self) -> None:
        for field_name, value in (
            ("inspected_count", self.inspected_count),
            ("succeeded_count", self.succeeded_count),
            ("failed_count", self.failed_count),
        ):
            if not isinstance(value, int):
                raise TypeError(f"{field_name} must be int")
            if value < 0:
                raise ValueError(f"{field_name} must be >= 0")
        if self.succeeded_count + self.failed_count != self.inspected_count:
            raise ValueError("pump result counts must add up")


@dataclass(frozen=True, slots=True)
class KnowledgeExtractionWorkflowRuntimePump:
    due_workflow_reader: DueKnowledgeExtractionWorkflowReaderPort
    workflow_runner: KnowledgeExtractionWorkflowRunnerPort

    async def run_once(
        self,
        *,
        limit: int,
    ) -> KnowledgeExtractionWorkflowRuntimePumpResult:
        if not isinstance(limit, int):
            raise TypeError("limit must be int")
        if limit <= 0:
            raise ValueError("limit must be > 0")

        due_workflows = await self.due_workflow_reader.list_due_workflows(limit=limit)
        succeeded_count = 0
        failed_count = 0

        for due_workflow in due_workflows:
            try:
                await self.workflow_runner.run(
                    project_id=due_workflow.project_id,
                    workflow_run_id=due_workflow.workflow_run_id,
                )
            except Exception:
                failed_count += 1
                LOGGER.exception(
                    "knowledge_extraction_workflow_runtime_pump_failed",
                    project_id=due_workflow.project_id,
                    workflow_run_id=due_workflow.workflow_run_id,
                )
                continue
            succeeded_count += 1

        return KnowledgeExtractionWorkflowRuntimePumpResult(
            inspected_count=len(due_workflows),
            succeeded_count=succeeded_count,
            failed_count=failed_count,
        )


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")
