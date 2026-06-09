from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_claim_extraction_stage_progress_query import (
    PostgresClaimExtractionStageProgressQuery,
)


@dataclass(frozen=True, slots=True)
class FakeRow:
    values: dict[str, object]

    def __getitem__(self, key: str) -> object:
        return self.values[key]


@dataclass(slots=True)
class FakeConnection:
    rows: list[FakeRow] = field(default_factory=list)
    artifact_count: object = 0
    fetch_calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)
    fetchval_calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)

    async def fetch(self, query: str, *args: object) -> list[FakeRow]:
        self.fetch_calls.append((query, args))
        return self.rows

    async def fetchval(self, query: str, *args: object) -> object:
        self.fetchval_calls.append((query, args))
        return self.artifact_count


def _now() -> datetime:
    return datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc)


def _leased_row() -> FakeRow:
    return FakeRow(
        {
            "work_item_id": "work-1",
            "work_kind": "knowledge_workbench.claim_extraction",
            "status": "leased",
            "attempt_count": 2,
            "leased_by": "worker-1",
            "lease_token": "lease-1",
            "lease_expires_at": _now() + timedelta(minutes=5),
            "next_attempt_at": None,
            "last_error_kind": None,
        },
    )


def _deferred_row() -> FakeRow:
    return FakeRow(
        {
            "work_item_id": "work-2",
            "work_kind": "knowledge_workbench.claim_extraction",
            "status": "deferred",
            "attempt_count": 1,
            "leased_by": None,
            "lease_token": None,
            "lease_expires_at": None,
            "next_attempt_at": _now() + timedelta(minutes=10),
            "last_error_kind": "quota_wait",
        },
    )


@pytest.mark.asyncio
async def test_load_work_items_reads_stage_index_and_maps_rows_to_work_items() -> None:
    connection = FakeConnection(rows=[_leased_row(), _deferred_row()])
    query = PostgresClaimExtractionStageProgressQuery(connection)

    work_items = await query.load_work_items(
        workflow_run_id="workflow-1",
        stage_run_id="stage-1",
    )

    assert len(work_items) == 2
    leased = work_items[0]
    deferred = work_items[1]
    assert leased.work_item_id == "work-1"
    assert leased.work_kind == WorkKind("knowledge_workbench.claim_extraction")
    assert leased.status is WorkItemStatus.LEASED
    assert leased.attempt_count == 2
    assert leased.leased_by == WorkerRef("worker-1")
    assert leased.lease_token == LeaseToken("lease-1")
    assert leased.lease_expires_at == _now() + timedelta(minutes=5)
    assert deferred.status is WorkItemStatus.DEFERRED
    assert deferred.next_attempt_at is not None
    assert deferred.next_attempt_at.value == _now() + timedelta(minutes=10)
    assert deferred.last_error_kind == "quota_wait"

    sql, args = connection.fetch_calls[0]
    assert "FROM claim_extraction_stage_work_items AS stage_items" in sql
    assert "JOIN execution_work_items AS wi" in sql
    assert "stage_items.workflow_run_id = $1" in sql
    assert "stage_items.stage_run_id = $2" in sql
    assert args == ("workflow-1", "stage-1")


@pytest.mark.asyncio
async def test_count_artifacts_reads_claim_observation_artifacts_by_payload_stage_refs() -> (
    None
):
    connection = FakeConnection(artifact_count=3)
    query = PostgresClaimExtractionStageProgressQuery(connection)

    count = await query.count_artifacts(
        workflow_run_id="workflow-1",
        stage_run_id="stage-1",
    )

    assert count == 3
    sql, args = connection.fetchval_calls[0]
    assert "FROM pipeline_artifacts" in sql
    assert "payload ->> 'workflow_run_id' = $1" in sql
    assert "payload ->> 'stage_run_id' = $2" in sql
    assert "artifact_kind LIKE 'knowledge_workbench.claim_observations.%'" in sql
    assert "status NOT IN ('rejected', 'expired')" in sql
    assert args == ("workflow-1", "stage-1")


@pytest.mark.asyncio
async def test_count_artifacts_rejects_non_integer_result() -> None:
    connection = FakeConnection(artifact_count="3")
    query = PostgresClaimExtractionStageProgressQuery(connection)

    with pytest.raises(TypeError, match="artifact count query must return int"):
        await query.count_artifacts(
            workflow_run_id="workflow-1",
            stage_run_id="stage-1",
        )


@pytest.mark.asyncio
async def test_load_work_items_rejects_malformed_rows() -> None:
    connection = FakeConnection(
        rows=[
            FakeRow(
                {
                    "work_item_id": "",
                    "work_kind": "knowledge_workbench.claim_extraction",
                    "status": "ready",
                    "attempt_count": 0,
                    "leased_by": None,
                    "lease_token": None,
                    "lease_expires_at": None,
                    "next_attempt_at": None,
                    "last_error_kind": None,
                },
            ),
        ],
    )
    query = PostgresClaimExtractionStageProgressQuery(connection)

    with pytest.raises(TypeError, match="work_item_id must be a non-empty string"):
        await query.load_work_items(
            workflow_run_id="workflow-1",
            stage_run_id="stage-1",
        )


def test_adapter_source_does_not_import_legacy_http_frontend_or_ignore_markers() -> (
    None
):
    source = Path(
        "src/contexts/knowledge_workbench/extraction/infrastructure/postgres/"
        "postgres_claim_extraction_stage_progress_query.py",
    ).read_text(encoding="utf-8")

    forbidden = (
        "workbench_observability_repository",
        "WorkbenchObservabilityRepository",
        "knowledge_workbench_section_batch_queue_items",
        "knowledge_workbench_registry_application_queue",
        "registry_application_queue",
        "knowledge_workbench_parallel_section_batch_plans",
        "workbench_parallel_processing",
        "KnowledgeWorkbenchRepository",
        "FaqWorkbenchSectionWorkItemLeaseService",
        "SectionBatchQueueItem",
        "ProcessingNodeRun",
        "ProcessingNodeArtifact",
        "FaqWorkbench",
        "src.infrastructure.",
        "src.application.workbench",
        "src.application.",
        "src.domain.project_plane.",
        "src.interfaces.",
        "fastapi",
        "APIRouter",
        "router.",
        "HTTPException",
        "src.contexts.llm_runtime.infrastructure",
        "Groq",
        "groq",
        "type: ignore",
        "A" + "ny",
    )

    offenders = [marker for marker in forbidden if marker in source]
    assert not offenders
