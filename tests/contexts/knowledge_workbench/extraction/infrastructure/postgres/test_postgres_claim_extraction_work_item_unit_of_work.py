from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
from src.contexts.artifact_runtime.domain.events.artifact_events import ArtifactStored
from src.contexts.artifact_runtime.domain.value_objects.artifact_kind import (
    ArtifactKind,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_lineage import (
    ArtifactLineage,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_payload import (
    ArtifactPayload,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_ref import ArtifactRef
from src.contexts.artifact_runtime.domain.value_objects.artifact_status import (
    ArtifactStatus,
)
from src.contexts.artifact_runtime.domain.value_objects.artifact_visibility import (
    ArtifactVisibility,
)
from src.contexts.artifact_runtime.domain.value_objects.retention_policy import (
    RetentionPolicy,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.entities.work_item_attempt import (
    WorkItemAttempt,
)
from src.contexts.execution_runtime.domain.events.work_item_events import (
    WorkItemCompleted,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.claim_extraction_runtime_mappers import (
    json_object,
    map_pipeline_artifact_lineage_to_rows,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_claim_extraction_work_item_unit_of_work import (
    PostgresClaimExtractionWorkItemUnitOfWork,
    UnitOfWorkClosedError,
)
from src.contexts.llm_runtime.domain.entities.llm_attempt import LlmAttempt
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.events.llm_task_events import LlmTaskSucceeded
from src.contexts.llm_runtime.domain.value_objects.input_ref import LlmInputRef
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute
from src.contexts.llm_runtime.domain.value_objects.llm_task_status import LlmTaskStatus
from src.contexts.llm_runtime.domain.value_objects.model_id import ModelId
from src.contexts.llm_runtime.domain.value_objects.output_contract_ref import (
    OutputContractRef,
)
from src.contexts.llm_runtime.domain.value_objects.prompt_version import PromptVersion
from src.contexts.llm_runtime.domain.value_objects.provider_account_ref import (
    ProviderAccountRef,
)
from src.contexts.llm_runtime.domain.value_objects.provider_id import ProviderId
from src.contexts.llm_runtime.domain.value_objects.token_usage import TokenUsage


@dataclass(slots=True)
class FakeTransaction:
    started: int = 0
    committed: int = 0
    rolled_back: int = 0
    fail_commit: bool = False

    async def start(self) -> None:
        self.started += 1

    async def commit(self) -> None:
        self.committed += 1
        if self.fail_commit:
            raise RuntimeError("commit failed")

    async def rollback(self) -> None:
        self.rolled_back += 1


@dataclass(slots=True)
class FakeConnection:
    transaction_obj: FakeTransaction = field(default_factory=FakeTransaction)
    calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    def transaction(self) -> FakeTransaction:
        return self.transaction_obj

    async def execute(self, query: str, *args: object) -> object:
        self.calls.append((query, args))
        return "OK"


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _leased_work_item() -> WorkItem:
    return WorkItem(
        work_item_id="work-1",
        work_kind=WorkKind("knowledge_workbench.claim_extraction"),
        status=WorkItemStatus.LEASED,
        attempt_count=1,
        leased_by=WorkerRef("worker-1"),
        lease_token=LeaseToken("lease-1"),
        lease_expires_at=_now(),
    )


def _work_item_attempt() -> WorkItemAttempt:
    return WorkItemAttempt(
        attempt_id="attempt-1",
        work_item_id="work-1",
        attempt_number=1,
        started_at=_now(),
        finished_at=_now(),
        outcome_status="completed",
    )


def _route() -> LlmRoute:
    return LlmRoute(
        provider_id=ProviderId("groq"),
        model_id=ModelId("qwen/qwen3-32b"),
        account_ref=ProviderAccountRef("slot-1"),
    )


def _llm_task() -> LlmTask:
    return LlmTask(
        task_id="task-1",
        prompt_id="prompt-a",
        prompt_version=PromptVersion("v1"),
        input_ref=LlmInputRef("source-unit-1"),
        output_contract_ref=OutputContractRef("claim_observations_json_v1"),
        status=LlmTaskStatus.SUCCEEDED,
        attempt_count=1,
        selected_route=_route(),
    )


def _llm_attempt() -> LlmAttempt:
    return LlmAttempt(
        attempt_id="llm-attempt-1",
        task_id="task-1",
        attempt_number=1,
        route=_route(),
        started_at=_now(),
        finished_at=_now(),
        usage=TokenUsage(input_tokens=10, output_tokens=5),
    )


def _artifact(*, with_parent: bool = False) -> PipelineArtifact:
    parent_refs = (ArtifactRef("parent-artifact-1"),) if with_parent else ()
    return PipelineArtifact(
        artifact_ref=ArtifactRef("artifact-1"),
        artifact_kind=ArtifactKind("knowledge_workbench.claim_observations.raw"),
        payload=ArtifactPayload({"claims": [{"claim": "A", "questions": ["Q"]}]}),
        status=ArtifactStatus.STORED,
        visibility=ArtifactVisibility.INTERNAL,
        retention_policy=RetentionPolicy.temporary(),
        lineage=ArtifactLineage(parent_refs),
        created_at=_now(),
        updated_at=_now(),
    )


def _queries(connection: FakeConnection) -> str:
    return "\n".join(query for query, _args in connection.calls)


@pytest.mark.asyncio
async def test_save_work_item_builds_sql_against_execution_work_items() -> None:
    connection = FakeConnection()
    unit_of_work = PostgresClaimExtractionWorkItemUnitOfWork(connection)

    await unit_of_work.save_work_item(_leased_work_item())

    assert "INSERT INTO execution_work_items" in _queries(connection)
    assert connection.transaction_obj.started == 1
    args = connection.calls[0][1]
    assert args[0] == "work-1"
    assert args[1] == "knowledge_workbench.claim_extraction"
    assert args[2] == "leased"
    assert args[4] == "worker-1"
    assert args[5] == "lease-1"


@pytest.mark.asyncio
async def test_save_work_item_attempt_builds_sql_against_execution_attempts() -> None:
    connection = FakeConnection()
    unit_of_work = PostgresClaimExtractionWorkItemUnitOfWork(connection)

    await unit_of_work.save_work_item_attempt(_work_item_attempt())

    assert "INSERT INTO execution_work_item_attempts" in _queries(connection)
    args = connection.calls[0][1]
    assert args[0] == "attempt-1"
    assert args[1] == "work-1"
    assert args[2] == 1
    assert args[5] == "completed"


@pytest.mark.asyncio
async def test_save_llm_task_builds_sql_against_llm_tasks() -> None:
    connection = FakeConnection()
    unit_of_work = PostgresClaimExtractionWorkItemUnitOfWork(connection)

    await unit_of_work.save_llm_task(_llm_task())

    assert "INSERT INTO llm_tasks" in _queries(connection)
    args = connection.calls[0][1]
    assert args[0] == "task-1"
    assert args[1] == "prompt-a"
    assert args[2] == "v1"
    assert args[5] == "succeeded"
    assert args[7] == "groq"
    assert args[8] == "qwen/qwen3-32b"
    assert args[9] == "slot-1"


@pytest.mark.asyncio
async def test_save_llm_attempt_builds_sql_against_llm_attempts() -> None:
    connection = FakeConnection()
    unit_of_work = PostgresClaimExtractionWorkItemUnitOfWork(connection)

    await unit_of_work.save_llm_attempt(_llm_attempt())

    assert "INSERT INTO llm_attempts" in _queries(connection)
    args = connection.calls[0][1]
    assert args[0] == "llm-attempt-1"
    assert args[1] == "task-1"
    assert args[3] == "groq"
    assert args[4] == "qwen/qwen3-32b"
    assert args[5] == "slot-1"
    assert args[8] == 10
    assert args[9] == 5


@pytest.mark.asyncio
async def test_save_artifact_builds_sql_against_pipeline_artifacts() -> None:
    connection = FakeConnection()
    unit_of_work = PostgresClaimExtractionWorkItemUnitOfWork(connection)

    await unit_of_work.save_artifact(_artifact())

    assert "INSERT INTO pipeline_artifacts" in _queries(connection)
    args = connection.calls[0][1]
    assert args[0] == "artifact-1"
    assert args[1] == "knowledge_workbench.claim_observations.raw"
    assert args[2] == "stored"
    assert args[3] == "internal"
    assert args[4] == "temporary"
    assert isinstance(args[5], dict)
    assert args[5] == {"claims": [{"claim": "A", "questions": ["Q"]}]}


@pytest.mark.asyncio
async def test_save_artifact_builds_lineage_sql_when_parent_refs_exist() -> None:
    connection = FakeConnection()
    unit_of_work = PostgresClaimExtractionWorkItemUnitOfWork(connection)

    await unit_of_work.save_artifact(_artifact(with_parent=True))

    queries = _queries(connection)
    assert "INSERT INTO pipeline_artifacts" in queries
    assert "INSERT INTO pipeline_artifact_lineage" in queries
    lineage_args = connection.calls[1][1]
    assert lineage_args == ("artifact-1", "parent-artifact-1")


def test_lineage_mapper_returns_empty_rows_for_empty_parent_refs() -> None:
    assert map_pipeline_artifact_lineage_to_rows(_artifact()) == ()


@pytest.mark.asyncio
async def test_append_event_builds_sql_against_outbox_events() -> None:
    connection = FakeConnection()
    unit_of_work = PostgresClaimExtractionWorkItemUnitOfWork(connection)

    await unit_of_work.append_event(
        WorkItemCompleted(work_item_id="work-1", occurred_at=_now()),
    )

    assert "INSERT INTO outbox_events" in _queries(connection)
    args = connection.calls[0][1]
    assert isinstance(args[0], str)
    assert args[1] == "WorkItemCompleted"
    assert args[2] == "work-1"
    assert isinstance(args[3], dict)
    assert args[3]["work_item_id"] == "work-1"


@pytest.mark.asyncio
async def test_append_event_maps_llm_and_artifact_aggregate_refs() -> None:
    connection = FakeConnection()
    unit_of_work = PostgresClaimExtractionWorkItemUnitOfWork(connection)

    await unit_of_work.append_event(
        LlmTaskSucceeded(task_id="task-1", occurred_at=_now())
    )
    await unit_of_work.append_event(
        ArtifactStored(artifact_ref=ArtifactRef("artifact-1"), occurred_at=_now()),
    )

    assert connection.calls[0][1][1] == "LlmTaskSucceeded"
    assert connection.calls[0][1][2] == "task-1"
    assert connection.calls[1][1][1] == "ArtifactStored"
    assert connection.calls[1][1][2] == "artifact-1"


@pytest.mark.asyncio
async def test_commit_commits_transaction_once() -> None:
    connection = FakeConnection()
    unit_of_work = PostgresClaimExtractionWorkItemUnitOfWork(connection)

    await unit_of_work.save_work_item(_leased_work_item())
    await unit_of_work.commit()

    assert connection.transaction_obj.started == 1
    assert connection.transaction_obj.committed == 1
    assert connection.transaction_obj.rolled_back == 0


@pytest.mark.asyncio
async def test_rollback_rolls_back_transaction() -> None:
    connection = FakeConnection()
    unit_of_work = PostgresClaimExtractionWorkItemUnitOfWork(connection)

    await unit_of_work.save_work_item(_leased_work_item())
    await unit_of_work.rollback()

    assert connection.transaction_obj.started == 1
    assert connection.transaction_obj.committed == 0
    assert connection.transaction_obj.rolled_back == 1


@pytest.mark.asyncio
async def test_commit_failure_rolls_back_and_closes_unit_of_work() -> None:
    transaction = FakeTransaction(fail_commit=True)
    connection = FakeConnection(transaction_obj=transaction)
    unit_of_work = PostgresClaimExtractionWorkItemUnitOfWork(connection)

    await unit_of_work.save_work_item(_leased_work_item())

    with pytest.raises(RuntimeError, match="commit failed"):
        await unit_of_work.commit()

    assert transaction.committed == 1
    assert transaction.rolled_back == 1

    with pytest.raises(UnitOfWorkClosedError):
        await unit_of_work.save_work_item(_leased_work_item())


@pytest.mark.asyncio
async def test_commit_without_open_transaction_is_noop_then_closes() -> None:
    connection = FakeConnection()
    unit_of_work = PostgresClaimExtractionWorkItemUnitOfWork(connection)

    await unit_of_work.commit()

    assert connection.transaction_obj.started == 0
    assert connection.transaction_obj.committed == 0

    with pytest.raises(UnitOfWorkClosedError):
        await unit_of_work.rollback()


def test_mapper_returns_jsonb_compatible_dict_payloads() -> None:
    payload = json_object(
        {
            "a": ("x", {"nested": (1, 2)}),
            "b": True,
        }
    )

    assert payload == {"a": ["x", {"nested": [1, 2]}], "b": True}
    assert isinstance(payload, dict)
    assert isinstance(payload["a"], list)


def test_adapter_source_does_not_contain_legacy_forbidden_strings() -> None:
    adapter_path = (
        "src/contexts/knowledge_workbench/extraction/infrastructure/postgres/"
        "postgres_claim_extraction_work_item_unit_of_work.py"
    )
    mapper_path = (
        "src/contexts/knowledge_workbench/extraction/infrastructure/postgres/"
        "claim_extraction_runtime_mappers.py"
    )

    source = "\n".join(
        [
            open(adapter_path, encoding="utf-8").read(),
            open(mapper_path, encoding="utf-8").read(),
        ]
    )

    forbidden = (
        "knowledge_workbench_section_batch_queue_items",
        "ProcessingNodeRun",
        "ProcessingNodeArtifact",
        "FaqWorkbench",
        "SectionBatchQueueItem",
        "src.infrastructure.db.knowledge_workbench_repository",
        "src.application.services.faq_workbench",
        "type: ignore",
    )

    offenders = [item for item in forbidden if item in source]
    assert not offenders
