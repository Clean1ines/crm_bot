from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest

from src.contexts.knowledge_workbench.extraction.application.read_models.claim_extraction_stage_progress import (
    ClaimExtractionStageProgressQuery,
    ClaimExtractionStageProgressStatus,
)
from src.contexts.knowledge_workbench.extraction.application.use_cases.run_claim_extraction_stage import (
    RunClaimExtractionStageCommand,
)
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.claim_extraction_stage_runtime import (
    make_claim_extraction_stage_postgres_runtime,
)
from src.contexts.knowledge_workbench.source_management.domain.entities.source_unit import (
    SourceUnit,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.heading_path import (
    HeadingPath,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_document_ref import (
    SourceDocumentRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_kind import (
    SourceUnitKind,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_lineage import (
    SourceUnitLineage,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_ref import (
    SourceUnitRef,
)
from src.contexts.knowledge_workbench.source_management.domain.value_objects.source_unit_text import (
    SourceUnitText,
)


@dataclass(slots=True)
class FakeTransaction:
    connection: FakeRuntimeConnection
    started: int = 0
    committed: int = 0
    rolled_back: int = 0

    async def start(self) -> None:
        self.started += 1
        self.connection.transaction_active = True
        self.connection.boundary_events.append("transaction.start")

    async def commit(self) -> None:
        self.committed += 1
        self.connection.boundary_events.append("transaction.commit")
        self.connection.commit_pending_writes()
        self.connection.transaction_active = False

    async def rollback(self) -> None:
        self.rolled_back += 1
        self.connection.boundary_events.append("transaction.rollback")
        self.connection.clear_pending_writes()
        self.connection.transaction_active = False


@dataclass(slots=True)
class FakeRow:
    values: dict[str, object]

    def __getitem__(self, key: str) -> object:
        return self.values[key]


@dataclass(slots=True)
class FakeRuntimeConnection:
    fail_on_stage_index_insert: bool = False
    work_items: dict[str, dict[str, object]] = field(default_factory=dict)
    stage_items: list[tuple[str, str, str]] = field(default_factory=list)
    pending_work_items: dict[str, dict[str, object]] = field(default_factory=dict)
    pending_stage_items: list[tuple[str, str, str]] = field(default_factory=list)
    execute_calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)
    fetch_calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)
    fetchval_calls: list[tuple[str, tuple[object, ...]]] = field(default_factory=list)
    boundary_events: list[str] = field(default_factory=list)
    transaction_active: bool = False
    transaction_obj: FakeTransaction = field(init=False)

    def __post_init__(self) -> None:
        self.transaction_obj = FakeTransaction(connection=self)

    def transaction(self) -> FakeTransaction:
        return self.transaction_obj

    def commit_pending_writes(self) -> None:
        self.work_items.update(self.pending_work_items)
        for item in self.pending_stage_items:
            if item not in self.stage_items:
                self.stage_items.append(item)
        self.clear_pending_writes()

    def clear_pending_writes(self) -> None:
        self.pending_work_items.clear()
        self.pending_stage_items.clear()

    async def execute(self, query: str, *args: object) -> object:
        self.execute_calls.append((query, args))
        if "INSERT INTO execution_work_items" in query:
            assert self.transaction_active is True
            self.boundary_events.append("write.execution_work_items")
            self.pending_work_items[str(args[0])] = {
                "work_item_id": args[0],
                "work_kind": args[1],
                "status": args[2],
                "attempt_count": args[3],
                "leased_by": args[4],
                "lease_token": args[5],
                "lease_expires_at": args[6],
                "next_attempt_at": args[7],
                "last_error_kind": args[8],
            }
            return "OK"
        if "INSERT INTO claim_extraction_stage_work_items" in query:
            assert self.transaction_active is True
            self.boundary_events.append("write.claim_extraction_stage_work_items")
            if self.fail_on_stage_index_insert:
                raise RuntimeError("stage index insert failed")
            item = (str(args[0]), str(args[1]), str(args[2]))
            if item not in self.pending_stage_items:
                self.pending_stage_items.append(item)
            return "OK"
        return "OK"

    async def fetch(self, query: str, *args: object) -> list[FakeRow]:
        assert self.transaction_active is False
        self.boundary_events.append("read.execution_work_items")
        self.fetch_calls.append((query, args))
        workflow_run_id = str(args[0])
        stage_run_id = str(args[1])
        rows: list[FakeRow] = []
        for saved_workflow_run_id, saved_stage_run_id, work_item_id in self.stage_items:
            if saved_workflow_run_id != workflow_run_id:
                continue
            if saved_stage_run_id != stage_run_id:
                continue
            rows.append(FakeRow(self.work_items[work_item_id]))
        return rows

    async def fetchval(self, query: str, *args: object) -> object:
        assert self.transaction_active is False
        self.boundary_events.append("read.pipeline_artifacts")
        self.fetchval_calls.append((query, args))
        return 0


def _now() -> datetime:
    return datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc)


def _source_unit(ref: str, *, ordinal: int) -> SourceUnit:
    return SourceUnit(
        unit_ref=SourceUnitRef(ref),
        document_ref=SourceDocumentRef("document-1"),
        unit_kind=SourceUnitKind.SECTION,
        text=SourceUnitText("Product answers user questions."),
        heading_path=HeadingPath(("Root",)),
        lineage=SourceUnitLineage(),
        ordinal=ordinal,
        created_at=_now(),
    )


def _command() -> RunClaimExtractionStageCommand:
    return RunClaimExtractionStageCommand(
        workflow_run_id="workflow-1",
        stage_run_id="stage-1",
        source_units=(
            _source_unit("unit-1", ordinal=0),
            _source_unit("unit-2", ordinal=1),
        ),
        prompt_id="faq_claim_observations",
    )


@pytest.mark.asyncio
async def test_postgres_runtime_start_then_progress_reads_indexed_work_items() -> None:
    connection = FakeRuntimeConnection()
    runtime = make_claim_extraction_stage_postgres_runtime(connection)

    start_result = await runtime.runner.execute(_command())
    progress = await runtime.progress_reader.execute(
        ClaimExtractionStageProgressQuery(
            workflow_run_id="workflow-1",
            stage_run_id="stage-1",
        ),
    )

    assert len(start_result.work_items) == 2
    assert connection.transaction_obj.started == 1
    assert connection.transaction_obj.committed == 1
    assert connection.transaction_obj.rolled_back == 0
    assert connection.transaction_active is False
    assert len(connection.work_items) == 2
    assert connection.pending_work_items == {}
    assert connection.pending_stage_items == []
    assert connection.stage_items == [
        ("workflow-1", "stage-1", start_result.work_items[0].work_item_id),
        ("workflow-1", "stage-1", start_result.work_items[1].work_item_id),
    ]
    assert connection.boundary_events == [
        "transaction.start",
        "write.execution_work_items",
        "write.claim_extraction_stage_work_items",
        "write.execution_work_items",
        "write.claim_extraction_stage_work_items",
        "transaction.commit",
        "read.execution_work_items",
        "read.pipeline_artifacts",
    ]
    assert progress.status is ClaimExtractionStageProgressStatus.PENDING
    assert progress.ready_count == 2
    assert progress.total_work_item_count == 2
    assert progress.artifacts_count == 0
    assert progress.blocker_kind is None
    assert connection.fetch_calls
    assert connection.fetchval_calls


@pytest.mark.asyncio
async def test_postgres_runtime_rolls_back_work_item_and_index_writes_together() -> (
    None
):
    connection = FakeRuntimeConnection(fail_on_stage_index_insert=True)
    runtime = make_claim_extraction_stage_postgres_runtime(connection)

    with pytest.raises(RuntimeError, match="stage index insert failed"):
        await runtime.runner.execute(_command())

    progress = await runtime.progress_reader.execute(
        ClaimExtractionStageProgressQuery(
            workflow_run_id="workflow-1",
            stage_run_id="stage-1",
        ),
    )

    assert connection.transaction_obj.started == 1
    assert connection.transaction_obj.committed == 0
    assert connection.transaction_obj.rolled_back == 1
    assert connection.transaction_active is False
    assert connection.work_items == {}
    assert connection.stage_items == []
    assert connection.pending_work_items == {}
    assert connection.pending_stage_items == []
    assert connection.boundary_events == [
        "transaction.start",
        "write.execution_work_items",
        "write.claim_extraction_stage_work_items",
        "transaction.rollback",
        "read.execution_work_items",
        "read.pipeline_artifacts",
    ]
    assert progress.status is ClaimExtractionStageProgressStatus.PENDING
    assert progress.total_work_item_count == 0
    assert progress.ready_count == 0
    assert progress.artifacts_count == 0
