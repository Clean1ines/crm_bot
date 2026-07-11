from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from src.contexts.knowledge_workbench.rag_eval.application.workflows.drain_workbench_rag_eval_workflow_commands import (
    DrainWorkbenchRagEvalWorkflowCommandsResult,
)
from src.interfaces.composition.workbench_rag_eval import (
    make_workbench_rag_eval_workflow_runtime,
    make_start_workbench_rag_eval_v2,
)
from src.interfaces.composition import (
    workbench_rag_eval_workflow_runtime as runtime_module,
)
from src.interfaces.composition.workbench_rag_eval_workflow_runtime import (
    WorkbenchRagEvalWorkflowRuntimeComposition,
)
from src.contexts.knowledge_workbench.rag_eval.application.workflows.workbench_rag_eval_work_kinds import (
    WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
)
from src.contexts.llm_runtime.infrastructure.config.llm_runtime_settings import (
    LlmRuntimeSettings,
)
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_dispatch_executor import (
    GroqDispatchExecutor,
)
from tests.interfaces.composition import (
    test_prepare_llm_dispatch_batch as prepare_fakes,
)


NOW = datetime(2026, 7, 11, 12, 0, tzinfo=timezone.utc)


@dataclass(slots=True)
class FakeRuntimeConnection:
    now: datetime = NOW
    commands: list[dict[str, object]] = field(default_factory=list)
    fetch_calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    async def fetch(self, query: str, *args: object) -> list[dict[str, object]]:
        self.fetch_calls.append((query, args))
        due_rows: list[dict[str, object]] = []
        seen: set[str] = set()
        for command in self.commands:
            if command["status"] != "PENDING":
                continue
            if command["run_status"] in {"completed", "blocked", "failed"}:
                continue
            if command["run_after"] > self.now:
                continue
            workflow_run_id = str(command["workflow_run_id"])
            if workflow_run_id in seen:
                continue
            seen.add(workflow_run_id)
            due_rows.append(
                {
                    "project_id": command["project_id"],
                    "workflow_run_id": workflow_run_id,
                }
            )
        return due_rows[: int(args[0])]


@dataclass(slots=True)
class FakeRuntimePool:
    connection: FakeRuntimeConnection
    acquire_count: int = 0
    release_count: int = 0

    async def acquire(self) -> FakeRuntimeConnection:
        self.acquire_count += 1
        return self.connection

    async def release(self, connection: object) -> None:
        assert connection is self.connection
        self.release_count += 1


@dataclass(slots=True)
class FakeUnitOfWork:
    connection: object
    start_count: int = 0
    commit_count: int = 0
    rollback_count: int = 0

    async def start(self) -> None:
        self.start_count += 1

    async def commit(self) -> None:
        self.commit_count += 1

    async def rollback(self) -> None:
        self.rollback_count += 1


class FakeDrain:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail

    async def execute(self, command, **kwargs):
        if self.fail:
            raise RuntimeError("boom")
        return DrainWorkbenchRagEvalWorkflowCommandsResult(
            workflow_run_id=command.workflow_run_id,
            inspected_count=1,
            dispatched_count=1,
            blocked_count=0,
            last_blocked_command_type=None,
            last_blocked_reason=None,
        )


@dataclass(slots=True)
class FakeLogger:
    exceptions: list[tuple[str, dict[str, object]]] = field(default_factory=list)

    def exception(self, event: str, **kwargs: object) -> None:
        self.exceptions.append((event, kwargs))


def _runtime(pool: FakeRuntimePool) -> WorkbenchRagEvalWorkflowRuntimeComposition:
    return WorkbenchRagEvalWorkflowRuntimeComposition(
        pool=pool,
        llm_executor=SimpleNamespace(),
        prepare_llm_dispatch_batch=SimpleNamespace(),
        execute_prepared_llm_dispatch_attempt=SimpleNamespace(),
        search_published_workbench_runtime=SimpleNamespace(),
    )


def _command(
    workflow_run_id: str,
    *,
    run_after: datetime = NOW,
    status: str = "PENDING",
    run_status: str = "running",
) -> dict[str, object]:
    return {
        "project_id": "11111111-1111-1111-1111-111111111111",
        "workflow_run_id": workflow_run_id,
        "run_after": run_after,
        "status": status,
        "run_status": run_status,
    }


def test_make_start_workbench_rag_eval_v2_does_not_require_llm_executor() -> None:
    composition = make_start_workbench_rag_eval_v2(pool=object())

    assert composition.pool is not None


def test_workflow_runtime_factory_wires_generic_runtime_and_four_groq_accounts() -> (
    None
):
    settings = LlmRuntimeSettings(
        groq_api_key="test-key-1",
        groq_api_key2="test-key-2",
        groq_api_key3="test-key-3",
        groq_api_key4="test-key-4",
    )

    composition = make_workbench_rag_eval_workflow_runtime(
        pool=object(),
        llm_runtime_settings=settings,
    )

    assert isinstance(composition.llm_executor, GroqDispatchExecutor)
    expected_refs = (
        "groq_org_primary",
        "groq_org_secondary",
        "groq_org_tertiary",
        "groq_org_quaternary",
    )
    assert tuple(composition.llm_executor.transports_by_account_ref) == expected_refs
    assert (
        len(
            {
                id(transport)
                for transport in composition.llm_executor.transports_by_account_ref.values()
            }
        )
        == 4
    )
    assert composition.prepare_llm_dispatch_batch.provider_account_refs == expected_refs
    registry = (
        composition.prepare_llm_dispatch_batch.dispatch_preparation_builder_registry
    )
    assert registry.builder_for(WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND)


def test_workflow_runtime_factory_reuses_generic_prepare_and_execute_boundaries() -> (
    None
):
    composition = make_workbench_rag_eval_workflow_runtime(
        pool=object(),
        llm_runtime_settings=LlmRuntimeSettings(groq_api_key="test-key"),
    )

    assert (
        type(composition.prepare_llm_dispatch_batch).__name__
        == "PrepareLlmDispatchBatch"
    )
    assert (
        type(composition.execute_prepared_llm_dispatch_attempt).__name__
        == "TransactionalExecutePreparedLlmDispatchAttempt"
    )


@pytest.mark.asyncio
async def test_workflow_runtime_four_account_prepare_integration_proof() -> None:
    expected_refs = (
        "groq_org_primary",
        "groq_org_secondary",
        "groq_org_tertiary",
        "groq_org_quaternary",
    )
    settings = LlmRuntimeSettings(
        groq_api_key="test-key-1",
        groq_api_key2="test-key-2",
        groq_api_key3="test-key-3",
        groq_api_key4="test-key-4",
    )
    connection = prepare_fakes._connection_with_due_items(8)
    for row in connection.work_items.values():
        row["work_kind"] = WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND.value
    for account_ref in expected_refs:
        connection.capacity_observations.append(
            {
                "provider": "groq",
                "account_ref": account_ref,
                "model_ref": "qwen/qwen3-32b",
                "remaining_minute_requests": 1,
                "remaining_minute_tokens": 3500,
                "remaining_daily_requests": 10,
                "remaining_daily_tokens": 50000,
                "minute_reset_at": NOW + timedelta(seconds=60),
                "daily_reset_at": NOW + timedelta(hours=1),
                "actual_prompt_tokens": None,
                "actual_completion_tokens": None,
                "actual_total_tokens": None,
                "outcome_class": "succeeded",
                "observed_at": prepare_fakes._now(),
            }
        )
    composition = make_workbench_rag_eval_workflow_runtime(
        pool=prepare_fakes.FakePool(connection=connection),
        llm_runtime_settings=settings,
    )

    assert isinstance(composition.llm_executor, GroqDispatchExecutor)
    assert tuple(composition.llm_executor.transports_by_account_ref) == expected_refs
    assert (
        len(
            {
                id(transport)
                for transport in composition.llm_executor.transports_by_account_ref.values()
            }
        )
        == 4
    )
    assert composition.prepare_llm_dispatch_batch.provider_account_refs == expected_refs

    first = await composition.prepare_llm_dispatch_batch.execute(
        prepare_fakes._command(
            work_kind=WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
            account_capacities=(),
            requested_items=4,
            now=prepare_fakes._now(),
            started_at=prepare_fakes._started_at(),
        )
    )

    selected_account_refs = {
        str(dispatch["llm_allocation_payload"]["account_ref"])
        for dispatch in connection.dispatches.values()
    }
    assert len(first.attempt_result.started_attempts) == 4
    assert selected_account_refs == set(expected_refs)
    assert {
        (
            str(observation["account_ref"]),
            str(observation["model_ref"]),
        )
        for observation in connection.capacity_observations
    } == {(account_ref, "qwen/qwen3-32b") for account_ref in expected_refs}
    assert {
        (str(item["account_ref"]), str(item["model_ref"]))
        for item in connection.capacity_reservations
    } == {(account_ref, "qwen/qwen3-32b") for account_ref in expected_refs}

    second = await composition.prepare_llm_dispatch_batch.execute(
        prepare_fakes._command(
            work_kind=WORKBENCH_RAG_EVAL_QUESTION_GENERATION_WORK_KIND,
            account_capacities=(),
            requested_items=4,
            now=prepare_fakes._now(),
            started_at=prepare_fakes._started_at(),
        )
    )

    assert second.attempt_result.started_attempts == ()
    assert len(connection.dispatches) == 4
    assert len(connection.capacity_reservations) == 4


@pytest.mark.asyncio
async def test_pump_selects_due_retrieval_workflow_and_filters_future_completed() -> (
    None
):
    connection = FakeRuntimeConnection(
        commands=[
            _command("run-due"),
            _command("run-future", run_after=NOW + timedelta(minutes=1)),
            _command("run-completed", run_status="completed"),
            _command("run-done-command", status="COMPLETED"),
        ]
    )
    workflows = await _runtime(FakeRuntimePool(connection))._list_due_workflows(
        limit=10
    )

    assert tuple(workflow.workflow_run_id for workflow in workflows) == ("run-due",)
    sql = connection.fetch_calls[0][0]
    assert "command.status = 'PENDING'" in sql
    assert "command.run_after <= NOW()" in sql
    assert "run.status NOT IN ('completed', 'blocked', 'failed')" in sql


@pytest.mark.asyncio
async def test_pump_selects_future_command_after_due_time() -> None:
    connection = FakeRuntimeConnection(
        now=NOW + timedelta(minutes=2),
        commands=[_command("run-future", run_after=NOW + timedelta(minutes=1))],
    )
    workflows = await _runtime(FakeRuntimePool(connection))._list_due_workflows(
        limit=10
    )

    assert tuple(workflow.workflow_run_id for workflow in workflows) == ("run-future",)


@pytest.mark.asyncio
async def test_run_due_once_failure_isolation_keeps_next_workflow(monkeypatch) -> None:
    connection = FakeRuntimeConnection(commands=[_command("run-a"), _command("run-b")])
    runtime = _runtime(FakeRuntimePool(connection))
    calls: list[str] = []
    logger = FakeLogger()

    async def fake_execute(self, *, workflow_run_id: str, max_commands: int):
        del self
        calls.append(workflow_run_id)
        if workflow_run_id == "run-a":
            raise RuntimeError("first failed")
        return DrainWorkbenchRagEvalWorkflowCommandsResult(
            workflow_run_id=workflow_run_id,
            inspected_count=1,
            dispatched_count=1,
            blocked_count=0,
            last_blocked_command_type=None,
            last_blocked_reason=None,
        )

    monkeypatch.setattr(
        runtime_module.WorkbenchRagEvalWorkflowRuntimeComposition,
        "execute",
        fake_execute,
    )
    monkeypatch.setattr(runtime_module, "LOGGER", logger)

    result = await runtime.run_due_once(workflow_batch_size=10, max_commands=1)

    assert calls == ["run-a", "run-b"]
    assert tuple(item.workflow_run_id for item in result.succeeded) == ("run-b",)
    assert len(result.failed) == 1
    assert result.failed[0].workflow_run_id == "run-a"
    assert result.failed[0].error_type == "RuntimeError"
    assert result.failed[0].error_message == "first failed"
    assert logger.exceptions == [
        (
            "workbench_rag_eval_workflow_run_failed",
            {
                "workflow_run_id": "run-a",
                "project_id": "11111111-1111-1111-1111-111111111111",
                "error_type": "RuntimeError",
                "error_message": "first failed",
            },
        )
    ]


@pytest.mark.asyncio
async def test_repeated_pump_does_not_duplicate_completed_transition(
    monkeypatch,
) -> None:
    command = _command("run-once")
    connection = FakeRuntimeConnection(commands=[command])
    runtime = _runtime(FakeRuntimePool(connection))
    calls: list[str] = []

    async def fake_execute(self, *, workflow_run_id: str, max_commands: int):
        del self
        calls.append(workflow_run_id)
        command["status"] = "COMPLETED"
        return DrainWorkbenchRagEvalWorkflowCommandsResult(
            workflow_run_id=workflow_run_id,
            inspected_count=1,
            dispatched_count=1,
            blocked_count=0,
            last_blocked_command_type=None,
            last_blocked_reason=None,
        )

    monkeypatch.setattr(
        runtime_module.WorkbenchRagEvalWorkflowRuntimeComposition,
        "execute",
        fake_execute,
    )

    first = await runtime.run_due_once(workflow_batch_size=10, max_commands=1)
    second = await runtime.run_due_once(workflow_batch_size=10, max_commands=1)

    assert tuple(item.workflow_run_id for item in first.succeeded) == ("run-once",)
    assert first.failed == ()
    assert second.succeeded == ()
    assert second.failed == ()
    assert calls == ["run-once"]


def test_run_due_once_source_does_not_swallow_exceptions_silently() -> None:
    import inspect

    source = inspect.getsource(
        runtime_module.WorkbenchRagEvalWorkflowRuntimeComposition.run_due_once
    )

    assert "LOGGER.exception" in source
    assert "WorkbenchRagEvalWorkflowRunFailure" in source
    assert "except Exception:\n                continue" not in source


@pytest.mark.asyncio
async def test_execute_commits_transaction_boundary(monkeypatch) -> None:
    connection = FakeRuntimeConnection()
    uows: list[FakeUnitOfWork] = []

    def fake_uow_factory(connection_arg):
        uow = FakeUnitOfWork(connection_arg)
        uows.append(uow)
        return uow

    monkeypatch.setattr(
        runtime_module, "PostgresWorkflowRuntimeUnitOfWork", fake_uow_factory
    )
    monkeypatch.setattr(
        runtime_module, "DrainWorkbenchRagEvalWorkflowCommands", lambda: FakeDrain()
    )

    result = await _runtime(FakeRuntimePool(connection)).execute(
        workflow_run_id="run-1", max_commands=1
    )

    assert result.workflow_run_id == "run-1"
    assert (uows[0].start_count, uows[0].commit_count, uows[0].rollback_count) == (
        1,
        1,
        0,
    )


@pytest.mark.asyncio
async def test_execute_rolls_back_transaction_boundary(monkeypatch) -> None:
    connection = FakeRuntimeConnection()
    uows: list[FakeUnitOfWork] = []

    def fake_uow_factory(connection_arg):
        uow = FakeUnitOfWork(connection_arg)
        uows.append(uow)
        return uow

    monkeypatch.setattr(
        runtime_module, "PostgresWorkflowRuntimeUnitOfWork", fake_uow_factory
    )
    monkeypatch.setattr(
        runtime_module,
        "DrainWorkbenchRagEvalWorkflowCommands",
        lambda: FakeDrain(fail=True),
    )

    with pytest.raises(RuntimeError, match="boom"):
        await _runtime(FakeRuntimePool(connection)).execute(
            workflow_run_id="run-1", max_commands=1
        )

    assert (uows[0].start_count, uows[0].commit_count, uows[0].rollback_count) == (
        1,
        0,
        1,
    )
