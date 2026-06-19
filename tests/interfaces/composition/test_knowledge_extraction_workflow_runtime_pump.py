from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from src.interfaces.composition.knowledge_extraction_workflow_runtime_pump import (
    DueKnowledgeExtractionWorkflow,
    KnowledgeExtractionWorkflowRuntimePump,
)


@dataclass
class FakeDueWorkflowReader:
    due: tuple[DueKnowledgeExtractionWorkflow, ...]
    requested_limits: list[int] = field(default_factory=list)

    async def list_due_workflows(
        self,
        *,
        limit: int,
    ) -> tuple[DueKnowledgeExtractionWorkflow, ...]:
        self.requested_limits.append(limit)
        return self.due


@dataclass
class FakeWorkflowRunner:
    failed_workflow_run_id: str | None = None
    calls: list[tuple[str, str]] = field(default_factory=list)

    async def run(
        self,
        *,
        project_id: str,
        workflow_run_id: str,
    ) -> None:
        self.calls.append((project_id, workflow_run_id))
        if workflow_run_id == self.failed_workflow_run_id:
            raise RuntimeError("synthetic workflow failure")


@pytest.mark.asyncio
async def test_pump_runs_due_workflow_without_http_poll() -> None:
    reader = FakeDueWorkflowReader(
        due=(
            DueKnowledgeExtractionWorkflow(
                project_id="project-1",
                workflow_run_id="workflow-1",
            ),
        )
    )
    runner = FakeWorkflowRunner()

    result = await KnowledgeExtractionWorkflowRuntimePump(
        due_workflow_reader=reader,
        workflow_runner=runner,
    ).run_once(limit=10)

    assert result.inspected_count == 1
    assert result.succeeded_count == 1
    assert result.failed_count == 0
    assert reader.requested_limits == [10]
    assert runner.calls == [("project-1", "workflow-1")]


@pytest.mark.asyncio
async def test_pump_isolates_one_workflow_failure() -> None:
    reader = FakeDueWorkflowReader(
        due=(
            DueKnowledgeExtractionWorkflow(
                project_id="project-1",
                workflow_run_id="workflow-failed",
            ),
            DueKnowledgeExtractionWorkflow(
                project_id="project-2",
                workflow_run_id="workflow-ok",
            ),
        )
    )
    runner = FakeWorkflowRunner(failed_workflow_run_id="workflow-failed")

    result = await KnowledgeExtractionWorkflowRuntimePump(
        due_workflow_reader=reader,
        workflow_runner=runner,
    ).run_once(limit=10)

    assert result.inspected_count == 2
    assert result.succeeded_count == 1
    assert result.failed_count == 1
    assert runner.calls == [
        ("project-1", "workflow-failed"),
        ("project-2", "workflow-ok"),
    ]
