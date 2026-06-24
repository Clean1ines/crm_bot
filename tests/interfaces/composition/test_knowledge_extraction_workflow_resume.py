from __future__ import annotations

from typing import cast

import pytest
from pathlib import Path

from src.contexts.capacity_admission_queue.application.build_capacity_admission_projection_candidates import (
    CapacityAdmissionLaneTarget,
)
from src.contexts.capacity_admission_queue.infrastructure.postgres.postgres_capacity_admission_projection_writer import (
    PostgresCapacityAdmissionProjectionWriter,
)
from src.contexts.knowledge_workbench.application.sagas.drain_knowledge_extraction_workflow_commands import (
    DrainKnowledgeExtractionWorkflowCommandsResult,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_draft_claim_observation_read_repository import (
    PostgresDraftClaimObservationReadRepository,
)
from src.interfaces.composition import (
    knowledge_extraction_workflow_resume as composition,
)
from src.interfaces.composition.knowledge_extraction_workflow_resume import (
    RunKnowledgeExtractionWorkflowResume,
)


class _FakeConnection:
    pass


class _FakePool:
    def __init__(self, connection: _FakeConnection) -> None:
        self.connection = connection
        self.released_connections: list[object] = []

    async def acquire(self) -> _FakeConnection:
        return self.connection

    async def release(self, connection: object) -> None:
        self.released_connections.append(connection)


class _FakeWorkflowRuntimeUnitOfWork:
    def __init__(self, connection: object) -> None:
        self.connection = connection
        self.started = False
        self.committed = False

    async def start(self) -> None:
        self.started = True

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        raise AssertionError("rollback must not be called")


@pytest.mark.asyncio
async def test_resume_passes_postgres_draft_claim_observation_read_repository_into_drain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection()
    pool = _FakePool(connection)
    captured_dependencies: dict[str, object] = {}

    async def fake_drain_execute(
        self: object,
        command: object,
        **dependencies: object,
    ) -> DrainKnowledgeExtractionWorkflowCommandsResult:
        del self, command
        captured_dependencies.update(dependencies)
        return DrainKnowledgeExtractionWorkflowCommandsResult(
            workflow_run_id="workflow-1",
            inspected_count=0,
            dispatched_count=0,
            blocked_count=0,
            last_blocked_command_type=None,
            last_blocked_reason=None,
        )

    monkeypatch.setattr(
        composition,
        "PostgresWorkflowRuntimeUnitOfWork",
        _FakeWorkflowRuntimeUnitOfWork,
    )
    monkeypatch.setattr(
        composition.DrainKnowledgeExtractionWorkflowCommands,
        "execute",
        fake_drain_execute,
    )

    runner = RunKnowledgeExtractionWorkflowResume(pool=pool)

    result = await runner._run_one_drain_transaction(
        workflow_run_id="workflow-1",
        max_commands=1,
    )

    repository = cast(
        PostgresDraftClaimObservationReadRepository,
        captured_dependencies["draft_claim_observation_read_repository"],
    )
    assert isinstance(repository, PostgresDraftClaimObservationReadRepository)
    assert repository._connection is connection
    assert result.workflow_run_id == "workflow-1"
    assert pool.released_connections == [connection]


@pytest.mark.asyncio
async def test_resume_passes_capacity_projection_writer_and_lane_target_into_drain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    connection = _FakeConnection()
    pool = _FakePool(connection)
    captured_dependencies: dict[str, object] = {}

    async def fake_drain_execute(
        self: object,
        command: object,
        **dependencies: object,
    ) -> DrainKnowledgeExtractionWorkflowCommandsResult:
        del self, command
        captured_dependencies.update(dependencies)
        return DrainKnowledgeExtractionWorkflowCommandsResult(
            workflow_run_id="workflow-1",
            inspected_count=0,
            dispatched_count=0,
            blocked_count=0,
            last_blocked_command_type=None,
            last_blocked_reason=None,
        )

    monkeypatch.setattr(
        composition,
        "PostgresWorkflowRuntimeUnitOfWork",
        _FakeWorkflowRuntimeUnitOfWork,
    )
    monkeypatch.setattr(
        composition.DrainKnowledgeExtractionWorkflowCommands,
        "execute",
        fake_drain_execute,
    )

    lane_target = CapacityAdmissionLaneTarget(
        provider="groq",
        account_ref=None,
        model_ref="qwen/qwen3-32b",
    )
    runner = RunKnowledgeExtractionWorkflowResume(
        pool=pool,
        capacity_admission_lane_target=lane_target,
    )

    await runner._run_one_drain_transaction(
        workflow_run_id="workflow-1",
        max_commands=1,
    )

    writer = cast(
        PostgresCapacityAdmissionProjectionWriter,
        captured_dependencies["capacity_admission_projection_writer"],
    )
    assert isinstance(writer, PostgresCapacityAdmissionProjectionWriter)
    assert writer._connection is connection
    assert captured_dependencies["capacity_admission_lane_target"] == lane_target


def test_resume_uses_workflow_wide_frontend_projection_composite() -> None:
    source = Path(composition.__file__).read_text(encoding="utf-8")

    assert "KnowledgeExtractionFrontendWorkflowEventProjector()" in source
    assert "ClaimBuilderFrontendWorkflowEventProjector()" not in source
