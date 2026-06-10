from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.contexts.artifact_runtime.domain.entities.pipeline_artifact import (
    PipelineArtifact,
)
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
from src.contexts.execution_runtime.application.ports.work_item_unit_of_work_port import (
    WorkItemEvent,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.entities.work_item_attempt import (
    WorkItemAttempt,
)
from src.contexts.execution_runtime.domain.value_objects.wait_until import WaitUntil
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.knowledge_workbench.extraction.application.use_cases.create_extraction_work_items import (
    CLAIM_EXTRACTION_WORK_KIND,
    CreateExtractionWorkItems,
    CreateExtractionWorkItemsCommand,
)
from src.contexts.knowledge_workbench.extraction.application.use_cases.resume_claim_extraction_stage import (
    ClaimExtractionStageArtifactRecord,
    ResumeClaimExtractionStage,
    ResumeClaimExtractionStageCommand,
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
class FakeResumeReader:
    artifacts: tuple[ClaimExtractionStageArtifactRecord, ...] = ()
    work_items: tuple[WorkItem, ...] = ()
    artifact_queries: list[tuple[str, str]] = field(default_factory=list)
    work_item_queries: list[tuple[str, str]] = field(default_factory=list)

    def load_completed_artifacts(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
    ) -> tuple[ClaimExtractionStageArtifactRecord, ...]:
        self.artifact_queries.append((workflow_run_id, stage_run_id))
        return self.artifacts

    def load_work_items(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
    ) -> tuple[WorkItem, ...]:
        self.work_item_queries.append((workflow_run_id, stage_run_id))
        return self.work_items


@dataclass(slots=True)
class FakeWorkItemUnitOfWork:
    saved_work_items: list[WorkItem] = field(default_factory=list)
    saved_attempts: list[WorkItemAttempt] = field(default_factory=list)
    events: list[WorkItemEvent] = field(default_factory=list)

    def save_work_item(self, item: WorkItem) -> None:
        self.saved_work_items.append(item)

    def save_attempt(self, attempt: WorkItemAttempt) -> None:
        self.saved_attempts.append(attempt)

    def append_event(self, event: WorkItemEvent) -> None:
        self.events.append(event)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


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


def _work_item_id(unit_ref: str, *, prompt_id: str = "faq_claim_observations") -> str:
    result = CreateExtractionWorkItems().execute(
        CreateExtractionWorkItemsCommand(
            source_units=(_source_unit(unit_ref),),
            prompt_id=prompt_id,
        ),
    )
    return result.work_items[0].work_item_id


def _work_item(
    unit_ref: str,
    *,
    status: WorkItemStatus = WorkItemStatus.READY,
) -> WorkItem:
    return WorkItem(
        work_item_id=_work_item_id(unit_ref),
        work_kind=CLAIM_EXTRACTION_WORK_KIND,
        status=status,
        next_attempt_at=WaitUntil(_now() + timedelta(hours=1))
        if status is WorkItemStatus.DEFERRED
        else None,
        last_error_kind="manual_stop"
        if status
        in {
            WorkItemStatus.DEFERRED,
            WorkItemStatus.RETRYABLE_FAILED,
            WorkItemStatus.TERMINAL_FAILED,
            WorkItemStatus.CANCELLED,
        }
        else None,
    )


def _artifact(
    unit_ref: str,
    *,
    status: ArtifactStatus = ArtifactStatus.STORED,
) -> ClaimExtractionStageArtifactRecord:
    artifact = PipelineArtifact(
        artifact_ref=ArtifactRef(f"artifact:{unit_ref}"),
        artifact_kind=ArtifactKind("knowledge_workbench.claim_observations.parsed"),
        payload=ArtifactPayload(
            {
                "workflow_run_id": "workflow-1",
                "stage_run_id": "stage-1",
                "source_unit_ref": unit_ref,
                "work_item_id": _work_item_id(unit_ref),
            },
        ),
        status=status,
        visibility=ArtifactVisibility.INTERNAL,
        retention_policy=RetentionPolicy.durable(),
        lineage=ArtifactLineage(),
        created_at=_now(),
        updated_at=_now(),
    )
    return ClaimExtractionStageArtifactRecord(
        artifact=artifact,
        work_item_id=_work_item_id(unit_ref),
        source_unit_ref=unit_ref,
    )


def _command(
    source_units: tuple[SourceUnit, ...] = (_source_unit("unit-1"),),
) -> ResumeClaimExtractionStageCommand:
    return ResumeClaimExtractionStageCommand(
        workflow_run_id="workflow-1",
        stage_run_id="stage-1",
        source_units=source_units,
        prompt_id="faq_claim_observations",
        now=_now(),
    )


def test_completed_artifact_prevents_duplicate_work_item_creation() -> None:
    reader = FakeResumeReader(
        artifacts=(_artifact("unit-1"),),
        work_items=(_work_item("unit-1", status=WorkItemStatus.COMPLETED),),
    )
    unit_of_work = FakeWorkItemUnitOfWork()

    result = ResumeClaimExtractionStage(
        reader=reader,
        repository=unit_of_work,
    ).execute(_command())

    assert result.summary.completed_count == 1
    assert result.summary.missing_count == 0
    assert result.summary.recreated_count == 0
    assert result.saved_work_items == ()
    assert unit_of_work.saved_work_items == []
    assert unit_of_work.committed is False


def test_missing_item_is_recreated() -> None:
    reader = FakeResumeReader()
    unit_of_work = FakeWorkItemUnitOfWork()

    result = ResumeClaimExtractionStage(
        reader=reader,
        repository=unit_of_work,
    ).execute(_command())

    assert result.summary.missing_count == 1
    assert result.summary.ready_count == 1
    assert result.summary.recreated_count == 1
    assert result.saved_work_items[0].work_item_id == _work_item_id("unit-1")
    assert result.saved_work_items[0].status is WorkItemStatus.READY
    assert unit_of_work.saved_work_items == list(result.saved_work_items)
    assert unit_of_work.committed is True


def test_deferred_item_remains_deferred_if_wait_until_future() -> None:
    reader = FakeResumeReader(
        work_items=(_work_item("unit-1", status=WorkItemStatus.DEFERRED),),
    )
    unit_of_work = FakeWorkItemUnitOfWork()

    result = ResumeClaimExtractionStage(
        reader=reader,
        repository=unit_of_work,
    ).execute(_command())

    assert result.summary.deferred_count == 1
    assert result.summary.ready_count == 0
    assert result.summary.recreated_count == 0
    assert unit_of_work.saved_work_items == []
    assert unit_of_work.committed is False


def test_retryable_item_can_be_returned_to_ready() -> None:
    reader = FakeResumeReader(
        work_items=(_work_item("unit-1", status=WorkItemStatus.RETRYABLE_FAILED),),
    )
    unit_of_work = FakeWorkItemUnitOfWork()

    result = ResumeClaimExtractionStage(
        reader=reader,
        repository=unit_of_work,
    ).execute(_command())

    assert result.summary.ready_count == 1
    assert result.summary.recreated_count == 1
    assert result.saved_work_items[0].status is WorkItemStatus.READY
    assert result.saved_work_items[0].last_error_kind is None
    assert unit_of_work.committed is True


def test_cancelled_terminal_item_is_not_resumed_automatically() -> None:
    reader = FakeResumeReader(
        work_items=(_work_item("unit-1", status=WorkItemStatus.CANCELLED),),
    )
    unit_of_work = FakeWorkItemUnitOfWork()

    result = ResumeClaimExtractionStage(
        reader=reader,
        repository=unit_of_work,
    ).execute(_command())

    assert result.summary.blocked_reason == "terminal_or_cancelled_work_item"
    assert result.summary.recreated_count == 0
    assert result.saved_work_items == ()
    assert unit_of_work.saved_work_items == []
    assert unit_of_work.committed is False


def test_cancelled_terminal_artifact_is_not_used_as_completed_resume_artifact() -> None:
    reader = FakeResumeReader(
        artifacts=(_artifact("unit-1", status=ArtifactStatus.REJECTED),),
    )
    unit_of_work = FakeWorkItemUnitOfWork()

    result = ResumeClaimExtractionStage(
        reader=reader,
        repository=unit_of_work,
    ).execute(_command())

    assert result.summary.completed_count == 0
    assert result.summary.missing_count == 1
    assert result.summary.recreated_count == 1


def test_resume_command_rejects_empty_refs_and_empty_source_units() -> None:
    with pytest.raises(ValueError, match="workflow_run_id must be non-empty"):
        ResumeClaimExtractionStageCommand(
            workflow_run_id="",
            stage_run_id="stage-1",
            source_units=(_source_unit("unit-1"),),
            prompt_id="faq_claim_observations",
            now=_now(),
        )

    with pytest.raises(ValueError, match="source_units must be non-empty"):
        ResumeClaimExtractionStageCommand(
            workflow_run_id="workflow-1",
            stage_run_id="stage-1",
            source_units=(),
            prompt_id="faq_claim_observations",
            now=_now(),
        )


def test_resume_reader_receives_workflow_and_stage_refs() -> None:
    reader = FakeResumeReader()
    unit_of_work = FakeWorkItemUnitOfWork()

    ResumeClaimExtractionStage(reader=reader, repository=unit_of_work).execute(
        _command(),
    )

    assert reader.artifact_queries == [("workflow-1", "stage-1")]
    assert reader.work_item_queries == [("workflow-1", "stage-1")]


def test_resume_source_does_not_import_legacy_checkpoint_statuses_or_db() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/extraction/application/use_cases/"
        "resume_claim_extraction_stage.py",
    ).read_text(encoding="utf-8")

    forbidden = (
        "CLAIM_OBSERVATIONS_PERSISTED",
        "REGISTRY_APPLICATION_QUEUED",
        "REGISTRY_APPLICATION_APPLIED",
        "SectionBatchQueueItem",
        "knowledge_workbench_section_batch_queue_items",
        "knowledge_workbench_parallel_section_batch_plans",
        "workbench_parallel_processing",
        "restore_checkpoint_service",
        "KnowledgeWorkbenchRepository",
        "FaqWorkbenchSectionWorkItemLeaseService",
        "ProcessingNodeRun",
        "ProcessingNodeArtifact",
        "FaqWorkbench",
        "src.infrastructure.",
        "src.application.",
        "src.domain.project_plane.",
        "src.interfaces.",
        "asyncpg",
        "Groq",
        "groq",
        "src.contexts.llm_runtime.infrastructure",
        "type: ignore",
    )

    offenders = [marker for marker in forbidden if marker in source]
    assert not offenders
