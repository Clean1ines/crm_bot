from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.contexts.execution_runtime.application.ports.work_item_unit_of_work_port import (
    WorkItemEvent,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.entities.work_item_attempt import (
    WorkItemAttempt,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.wait_until import WaitUntil
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.knowledge_workbench.extraction.application.use_cases.create_extraction_work_items import (
    CLAIM_EXTRACTION_WORK_KIND,
    CreateExtractionWorkItemsResult,
)
from src.contexts.knowledge_workbench.extraction.application.use_cases.run_claim_extraction_stage import (
    ClaimExtractionStageStatus,
    RunClaimExtractionStage,
    RunClaimExtractionStageCommand,
    claim_extraction_stage_readiness,
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
class FakeWorkItemUnitOfWork:
    saved_work_items: list[WorkItem] = field(default_factory=list)
    saved_attempts: list[WorkItemAttempt] = field(default_factory=list)
    events: list[WorkItemEvent] = field(default_factory=list)
    committed: bool = False
    rolled_back: bool = False
    fail_on_save: bool = False

    def save_work_item(self, item: WorkItem) -> None:
        if self.fail_on_save:
            raise RuntimeError("save failed")
        self.saved_work_items.append(item)

    def save_attempt(self, attempt: WorkItemAttempt) -> None:
        self.saved_attempts.append(attempt)

    def append_event(self, event: WorkItemEvent) -> None:
        self.events.append(event)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


@dataclass(slots=True)
class FakeStageWorkItemIndex:
    saved: list[tuple[str, str, WorkItem]] = field(default_factory=list)
    fail_on_save: bool = False

    def save_stage_work_item(
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
    received_source_units: tuple[SourceUnit, ...] = ()
    received_prompt_id: str | None = None

    def execute(self, command: object) -> CreateExtractionWorkItemsResult:
        self.received_source_units = getattr(command, "source_units")
        self.received_prompt_id = getattr(command, "prompt_id")
        return CreateExtractionWorkItemsResult(work_items=self.work_items)


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _source_unit(ref: str, *, ordinal: int = 0) -> SourceUnit:
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


def _work_item(
    ref: str,
    *,
    status: WorkItemStatus = WorkItemStatus.READY,
) -> WorkItem:
    if status is WorkItemStatus.LEASED:
        return WorkItem(
            work_item_id=ref,
            work_kind=CLAIM_EXTRACTION_WORK_KIND,
            status=status,
            attempt_count=1,
            leased_by=WorkerRef("worker-1"),
            lease_token=LeaseToken("lease-1"),
            lease_expires_at=_now() + timedelta(seconds=30),
        )

    if status is WorkItemStatus.DEFERRED:
        return WorkItem(
            work_item_id=ref,
            work_kind=CLAIM_EXTRACTION_WORK_KIND,
            status=status,
            attempt_count=1,
            next_attempt_at=WaitUntil(_now() + timedelta(seconds=60)),
            last_error_kind="minute_limit",
        )

    if status is WorkItemStatus.RETRYABLE_FAILED:
        return WorkItem(
            work_item_id=ref,
            work_kind=CLAIM_EXTRACTION_WORK_KIND,
            status=status,
            attempt_count=1,
            next_attempt_at=WaitUntil(_now() + timedelta(seconds=60)),
            last_error_kind="validation_failed",
        )

    if status is WorkItemStatus.TERMINAL_FAILED:
        return WorkItem(
            work_item_id=ref,
            work_kind=CLAIM_EXTRACTION_WORK_KIND,
            status=status,
            attempt_count=1,
            last_error_kind="auth_error",
        )

    return WorkItem(
        work_item_id=ref,
        work_kind=CLAIM_EXTRACTION_WORK_KIND,
        status=status,
    )


def _command(
    source_units: tuple[SourceUnit, ...] = (_source_unit("unit-1"),),
) -> RunClaimExtractionStageCommand:
    return RunClaimExtractionStageCommand(
        workflow_run_id="workflow-1",
        stage_run_id="stage-1",
        source_units=source_units,
        prompt_id="faq_claim_observations",
    )


def test_empty_source_units_rejected() -> None:
    with pytest.raises(ValueError, match="source_units must be non-empty"):
        RunClaimExtractionStageCommand(
            workflow_run_id="workflow-1",
            stage_run_id="stage-1",
            source_units=(),
            prompt_id="faq_claim_observations",
        )


def test_stage_refs_are_required() -> None:
    with pytest.raises(ValueError, match="workflow_run_id must be non-empty"):
        RunClaimExtractionStageCommand(
            workflow_run_id="",
            stage_run_id="stage-1",
            source_units=(_source_unit("unit-1"),),
            prompt_id="faq_claim_observations",
        )

    with pytest.raises(ValueError, match="stage_run_id must be non-empty"):
        RunClaimExtractionStageCommand(
            workflow_run_id="workflow-1",
            stage_run_id="",
            source_units=(_source_unit("unit-1"),),
            prompt_id="faq_claim_observations",
        )


def test_stage_runner_creates_saves_and_indexes_claim_extraction_work_items() -> None:
    unit_of_work = FakeWorkItemUnitOfWork()
    stage_index = FakeStageWorkItemIndex()
    source_units = (_source_unit("unit-1"), _source_unit("unit-2", ordinal=1))

    result = RunClaimExtractionStage(
        unit_of_work=unit_of_work,
        stage_work_item_index=stage_index,
    ).execute(_command(source_units=source_units))

    assert len(result.work_items) == 2
    assert all(
        item.work_kind == CLAIM_EXTRACTION_WORK_KIND for item in result.work_items
    )
    assert unit_of_work.saved_work_items == list(result.work_items)
    assert stage_index.saved == [
        ("workflow-1", "stage-1", result.work_items[0]),
        ("workflow-1", "stage-1", result.work_items[1]),
    ]
    assert unit_of_work.saved_attempts == []
    assert unit_of_work.events == []
    assert unit_of_work.committed is True
    assert unit_of_work.rolled_back is False
    assert result.readiness.status is ClaimExtractionStageStatus.PENDING


def test_stage_runner_accepts_fake_creator_and_passes_source_units_and_prompt_id() -> (
    None
):
    source_units = (_source_unit("unit-1"),)
    creator = FakeWorkItemCreator(work_items=(_work_item("work-1"),))
    unit_of_work = FakeWorkItemUnitOfWork()
    stage_index = FakeStageWorkItemIndex()

    result = RunClaimExtractionStage(
        unit_of_work=unit_of_work,
        stage_work_item_index=stage_index,
        work_item_creator=creator,
    ).execute(
        RunClaimExtractionStageCommand(
            workflow_run_id="workflow-1",
            stage_run_id="stage-1",
            source_units=source_units,
            prompt_id="prompt-a",
        ),
    )

    assert creator.received_source_units == source_units
    assert creator.received_prompt_id == "prompt-a"
    assert result.work_items == (_work_item("work-1"),)
    assert stage_index.saved == [("workflow-1", "stage-1", _work_item("work-1"))]


def test_stage_runner_rolls_back_when_work_item_save_fails() -> None:
    unit_of_work = FakeWorkItemUnitOfWork(fail_on_save=True)
    stage_index = FakeStageWorkItemIndex()

    with pytest.raises(RuntimeError, match="save failed"):
        RunClaimExtractionStage(
            unit_of_work=unit_of_work,
            stage_work_item_index=stage_index,
        ).execute(_command())

    assert unit_of_work.committed is False
    assert unit_of_work.rolled_back is True
    assert stage_index.saved == []


def test_stage_runner_rolls_back_when_stage_index_save_fails() -> None:
    unit_of_work = FakeWorkItemUnitOfWork()
    stage_index = FakeStageWorkItemIndex(fail_on_save=True)

    with pytest.raises(RuntimeError, match="index save failed"):
        RunClaimExtractionStage(
            unit_of_work=unit_of_work,
            stage_work_item_index=stage_index,
        ).execute(_command())

    assert unit_of_work.saved_work_items
    assert unit_of_work.committed is False
    assert unit_of_work.rolled_back is True


def test_stage_readiness_pending_and_in_progress() -> None:
    pending = claim_extraction_stage_readiness(
        (_work_item("work-1", status=WorkItemStatus.READY),),
    )
    in_progress = claim_extraction_stage_readiness(
        (_work_item("work-1", status=WorkItemStatus.LEASED),),
    )

    assert pending.status is ClaimExtractionStageStatus.PENDING
    assert pending.ready_count == 1
    assert in_progress.status is ClaimExtractionStageStatus.IN_PROGRESS
    assert in_progress.leased_count == 1


def test_stage_readiness_waiting_user_completed_and_failed() -> None:
    waiting = claim_extraction_stage_readiness(
        (_work_item("work-1", status=WorkItemStatus.DEFERRED),),
    )
    user_action = claim_extraction_stage_readiness(
        (_work_item("work-1", status=WorkItemStatus.USER_ACTION_REQUIRED),),
    )
    completed = claim_extraction_stage_readiness(
        (_work_item("work-1", status=WorkItemStatus.COMPLETED),),
    )
    failed = claim_extraction_stage_readiness(
        (_work_item("work-1", status=WorkItemStatus.TERMINAL_FAILED),),
    )

    assert waiting.status is ClaimExtractionStageStatus.WAITING_FOR_QUOTA
    assert user_action.status is ClaimExtractionStageStatus.USER_ACTION_REQUIRED
    assert completed.status is ClaimExtractionStageStatus.COMPLETED
    assert failed.status is ClaimExtractionStageStatus.FAILED


def test_stage_runner_source_does_not_import_llm_provider_db_or_legacy_queue() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/extraction/application/use_cases/"
        "run_claim_extraction_stage.py",
    ).read_text(encoding="utf-8")

    forbidden = (
        "src.contexts.llm_runtime",
        "src.infrastructure.",
        "src.application.",
        "src.domain.project_plane.",
        "src.interfaces.",
        "Groq",
        "groq",
        "asyncpg",
        "connection.execute",
        "fetchrow",
        "knowledge_workbench_section_batch_queue_items",
        "knowledge_workbench_parallel_section_batch_plans",
        "workbench_parallel_processing",
        "FaqWorkbenchSectionWorkItemLeaseService",
        "KnowledgeWorkbenchRepository",
        "ProcessingNodeRun",
        "ProcessingNodeArtifact",
        "SectionBatchQueueItem",
        "FaqWorkbench",
        "Prompt C",
        "registry_application",
        "type: ignore",
    )

    offenders = [marker for marker in forbidden if marker in source]
    assert not offenders


def test_source_management_application_stays_clean_of_claim_extraction_runtime() -> (
    None
):
    root = Path("src/contexts/knowledge_workbench/source_management/application")
    source = "\n".join(path.read_text(encoding="utf-8") for path in root.rglob("*.py"))

    forbidden = (
        "src.contexts.execution_runtime",
        "src.contexts.llm_runtime",
        "claim_extraction",
        "WorkItem",
        "WorkKind",
        "prompt_id",
        "type: ignore",
    )

    offenders = [marker for marker in forbidden if marker in source]
    assert not offenders
