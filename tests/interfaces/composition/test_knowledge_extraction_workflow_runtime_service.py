from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from types import SimpleNamespace

import pytest

from src.interfaces.composition import knowledge_extraction_workflow_runtime_service as service
from src.interfaces.composition.knowledge_extraction_workflow_runtime_pump import (
    DueKnowledgeExtractionWorkflow,
)


class FakeTransaction:
    async def __aenter__(self) -> None:
        return None

    async def __aexit__(
        self,
        exc_type: object,
        exc: object,
        traceback: object,
    ) -> None:
        return None


class FakeConnection:
    executed: list[str]

    def __init__(self) -> None:
        self.executed = []

    def transaction(self) -> FakeTransaction:
        return FakeTransaction()

    async def execute(self, query: str) -> str:
        self.executed.append(query)
        return "SET"


@dataclass
class FakePool:
    connection: FakeConnection = field(default_factory=FakeConnection)
    acquire_count: int = 0
    release_count: int = 0

    async def acquire(self) -> FakeConnection:
        self.acquire_count += 1
        return self.connection

    async def release(self, connection: object) -> None:
        assert connection is self.connection
        self.release_count += 1


@dataclass
class FakeExpiredLeaseRecoveryRepository:
    connection: object

    async def reclaim_expired(
        self,
        *,
        now: object,
        limit: int,
    ) -> SimpleNamespace:
        return SimpleNamespace(
            reclaimed_count=0,
            reclaimed_work_item_ids=(),
        )


@dataclass
class FakeDueWorkflowReader:
    connection: object

    async def list_due_workflows(
        self,
        *,
        limit: int,
    ) -> tuple[DueKnowledgeExtractionWorkflow, ...]:
        return (
            DueKnowledgeExtractionWorkflow(
                project_id="project-1",
                workflow_run_id="workflow-1",
            ),
        )


@dataclass
class ExplodingThenRecoveringPump:
    due_workflow_reader: object
    workflow_runner: object

    calls: int = 0

    async def run_once(self, *, limit: int) -> SimpleNamespace:
        type(self).calls += 1
        if type(self).calls == 1:
            raise RuntimeError("synthetic pump failure")
        return SimpleNamespace(
            inspected_count=1,
            succeeded_count=1,
            failed_count=0,
        )


@dataclass
class FakeRagEvalRuntime:
    shutdown_event: asyncio.Event
    calls: int = 0

    async def run_due_once(
        self,
        *,
        workflow_batch_size: int,
        max_commands: int,
    ) -> None:
        self.calls += 1
        if self.calls >= 2:
            self.shutdown_event.set()


@pytest.mark.asyncio
async def test_runtime_loop_survives_workflow_pump_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shutdown_event = asyncio.Event()
    pool = FakePool()
    rag_eval_runtime = FakeRagEvalRuntime(shutdown_event=shutdown_event)
    ExplodingThenRecoveringPump.calls = 0

    monkeypatch.setattr(
        service,
        "PostgresExpiredLeaseRecoveryRepository",
        FakeExpiredLeaseRecoveryRepository,
    )
    monkeypatch.setattr(
        service,
        "PostgresDueKnowledgeExtractionWorkflowReader",
        FakeDueWorkflowReader,
    )
    monkeypatch.setattr(
        service,
        "KnowledgeExtractionWorkflowRuntimePump",
        ExplodingThenRecoveringPump,
    )
    monkeypatch.setattr(
        service,
        "make_workbench_rag_eval_workflow_runtime",
        lambda **kwargs: rag_eval_runtime,
    )

    await asyncio.wait_for(
        service.run_knowledge_extraction_workflow_runtime_loop(
            pool=pool,
            llm_executor=object(),
            shutdown_event=shutdown_event,
            poll_interval_seconds=0.01,
            workflow_batch_size=10,
            max_drain_commands=20,
            stale_lease_batch_size=100,
        ),
        timeout=1,
    )

    assert ExplodingThenRecoveringPump.calls == 2
    assert pool.acquire_count == 2
    assert pool.release_count == 2
    assert "SET LOCAL lock_timeout" in pool.connection.executed[0]
