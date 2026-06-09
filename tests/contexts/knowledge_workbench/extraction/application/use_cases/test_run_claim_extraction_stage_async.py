from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.extraction.application.use_cases.create_extraction_work_items import (
    CreateExtractionWorkItemsResult,
)
from src.contexts.knowledge_workbench.extraction.application.use_cases.run_claim_extraction_stage import (
    ClaimExtractionStageStatus,
    RunClaimExtractionStageCommand,
)
from src.contexts.knowledge_workbench.extraction.application.use_cases.run_claim_extraction_stage_async import (
    RunClaimExtractionStageAsync,
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
class FakeAsyncWorkItemUnitOfWork:
    saved_work_items: list[WorkItem] = field(default_factory=list)
    committed: bool = False
    rolled_back: bool = False
    fail_on_save: bool = False

    async def save_work_item(self, item: WorkItem) -> None:
        if self.fail_on_save:
            raise RuntimeError("save failed")
        self.saved_work_items.append(item)

    async def commit(self) -> None:
        self.committed = True

    async def rollback(self) -> None:
        self.rolled_back = True


@dataclass(slots=True)
class FakeAsyncStageWorkItemIndex:
    saved: list[tuple[str, str, WorkItem]] = field(default_factory=list)
    fail_on_save: bool = False

    async def save_stage_work_item(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
        work_item: WorkItem,
    ) -> None:
        if self.fail_on_save:
            raise RuntimeError("index save failed")
        self.saved.append((workflow_run_id, stage_run_id, work_item))


@dataclass(slots=True)
class FakeWorkItemCreator:
    work_items: tuple[WorkItem, ...]

    def execute(self, command: object) -> CreateExtractionWorkItemsResult:
        return CreateExtractionWorkItemsResult(work_items=self.work_items)


def _now() -> datetime:
    return datetime(2026, 6, 9, 12, 0, tzinfo=timezone.utc)


def _source_unit(ref: str) -> SourceUnit:
    return SourceUnit(
        unit_ref=SourceUnitRef(ref),
        document_ref=SourceDocumentRef("document-1"),
        unit_kind=SourceUnitKind.SECTION,
        text=SourceUnitText("Product answers user questions."),
        heading_path=HeadingPath(("Root",)),
        lineage=SourceUnitLineage(),
        ordinal=0,
        created_at=_now(),
    )


def _work_item(ref: str) -> WorkItem:
    return WorkItem(
        work_item_id=ref,
        work_kind=WorkKind("knowledge_workbench.claim_extraction"),
    )


def _command() -> RunClaimExtractionStageCommand:
    return RunClaimExtractionStageCommand(
        workflow_run_id="workflow-1",
        stage_run_id="stage-1",
        source_units=(_source_unit("unit-1"),),
        prompt_id="faq_claim_observations",
    )


@pytest.mark.asyncio
async def test_async_stage_runner_awaits_work_item_and_index_writes() -> None:
    unit_of_work = FakeAsyncWorkItemUnitOfWork()
    stage_index = FakeAsyncStageWorkItemIndex()
    work_item = _work_item("work-1")

    result = await RunClaimExtractionStageAsync(
        unit_of_work=unit_of_work,
        stage_work_item_index=stage_index,
        work_item_creator=FakeWorkItemCreator(work_items=(work_item,)),
    ).execute(_command())

    assert result.work_items == (work_item,)
    assert result.readiness.status is ClaimExtractionStageStatus.PENDING
    assert unit_of_work.saved_work_items == [work_item]
    assert stage_index.saved == [("workflow-1", "stage-1", work_item)]
    assert unit_of_work.committed is True
    assert unit_of_work.rolled_back is False


@pytest.mark.asyncio
async def test_async_stage_runner_rolls_back_when_index_write_fails() -> None:
    unit_of_work = FakeAsyncWorkItemUnitOfWork()
    stage_index = FakeAsyncStageWorkItemIndex(fail_on_save=True)

    with pytest.raises(RuntimeError, match="index save failed"):
        await RunClaimExtractionStageAsync(
            unit_of_work=unit_of_work,
            stage_work_item_index=stage_index,
            work_item_creator=FakeWorkItemCreator(work_items=(_work_item("work-1"),)),
        ).execute(_command())

    assert unit_of_work.saved_work_items == [_work_item("work-1")]
    assert unit_of_work.committed is False
    assert unit_of_work.rolled_back is True


def test_sync_runner_does_not_import_async_postgres_writer_directly() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/extraction/application/use_cases/"
        "run_claim_extraction_stage.py",
    ).read_text(encoding="utf-8")

    assert "postgres_claim_extraction_stage_work_item_index" not in source
    assert "async def" not in source
    assert "await " not in source


def test_async_runner_source_does_not_import_postgres_or_legacy() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/extraction/application/use_cases/"
        "run_claim_extraction_stage_async.py",
    ).read_text(encoding="utf-8")

    forbidden = (
        "src.infrastructure.",
        "src.application.",
        "src.domain.project_plane.",
        "src.interfaces.",
        "Postgres",
        "asyncpg",
        "connection.execute",
        "knowledge_workbench_section_batch_queue_items",
        "knowledge_workbench_parallel_section_batch_plans",
        "workbench_parallel_processing",
        "KnowledgeWorkbenchRepository",
        "FaqWorkbenchSectionWorkItemLeaseService",
        "SectionBatchQueueItem",
        "ProcessingNodeRun",
        "ProcessingNodeArtifact",
        "FaqWorkbench",
        "type: ignore",
        "Any",
    )

    offenders = [marker for marker in forbidden if marker in source]
    assert not offenders
