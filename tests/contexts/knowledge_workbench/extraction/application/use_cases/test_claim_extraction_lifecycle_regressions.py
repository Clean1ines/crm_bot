from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

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
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    WorkItemStateMachine,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.knowledge_workbench.extraction.application.use_cases.cancel_claim_extraction_stage import (
    CancelClaimExtractionStage,
    CancelClaimExtractionStageCommand,
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

    def load_completed_artifacts(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
    ) -> tuple[ClaimExtractionStageArtifactRecord, ...]:
        return self.artifacts

    def load_work_items(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
    ) -> tuple[WorkItem, ...]:
        return self.work_items


@dataclass(slots=True)
class FakeWorkItemUnitOfWork:
    saved_work_items: list[WorkItem] = field(default_factory=list)

    def save_work_item(self, item: WorkItem) -> None:
        self.saved_work_items.append(item)

    def save_attempt(self, attempt: object) -> None:
        raise AssertionError("resume regression test must not save attempts")

    def append_event(self, event: object) -> None:
        raise AssertionError("resume regression test must not append events")

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


@dataclass(slots=True)
class FakeCancelReader:
    work_items: tuple[WorkItem, ...]

    def load_work_items(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
    ) -> tuple[WorkItem, ...]:
        return self.work_items


@dataclass(slots=True)
class FakeCancelUnitOfWork:
    saved_work_items: list[WorkItem] = field(default_factory=list)
    events: list[object] = field(default_factory=list)

    def save_work_item(self, item: WorkItem) -> None:
        self.saved_work_items.append(item)

    def append_event(self, event: object) -> None:
        self.events.append(event)

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


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


def _work_item_id(unit_ref: str, *, prompt_id: str = "faq_claim_observations") -> str:
    result = CreateExtractionWorkItems().execute(
        CreateExtractionWorkItemsCommand(
            source_units=(_source_unit(unit_ref),),
            prompt_id=prompt_id,
        ),
    )
    return result.work_items[0].work_item_id


def _leased_claim_extraction_work_item(unit_ref: str) -> WorkItem:
    return WorkItemStateMachine.lease_ready(
        WorkItem(
            work_item_id=_work_item_id(unit_ref),
            work_kind=CLAIM_EXTRACTION_WORK_KIND,
        ),
        worker=WorkerRef("worker-1"),
        lease_token=LeaseToken("lease-1"),
        lease_expires_at=_now() + timedelta(minutes=5),
        now=_now(),
    )


def _completed_artifact(unit_ref: str) -> ClaimExtractionStageArtifactRecord:
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
        status=ArtifactStatus.STORED,
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


def test_resume_persists_leased_work_item_as_ready_before_counting_it_ready() -> None:
    leased = _leased_claim_extraction_work_item("unit-1")
    unit_of_work = FakeWorkItemUnitOfWork()

    result = ResumeClaimExtractionStage(
        reader=FakeResumeReader(work_items=(leased,)),
        repository=unit_of_work,
    ).execute(
        ResumeClaimExtractionStageCommand(
            workflow_run_id="workflow-1",
            stage_run_id="stage-1",
            source_units=(_source_unit("unit-1"),),
            prompt_id="faq_claim_observations",
            now=_now(),
        ),
    )

    assert result.summary.ready_count == 1
    assert result.summary.recreated_count == 1
    assert len(result.saved_work_items) == 1
    assert result.saved_work_items[0].status is WorkItemStatus.READY
    assert result.saved_work_items[0].work_item_id == leased.work_item_id
    assert result.saved_work_items[0].work_kind == leased.work_kind
    assert result.saved_work_items[0].attempt_count == leased.attempt_count
    assert result.saved_work_items[0].leased_by is None
    assert result.saved_work_items[0].lease_token is None
    assert result.saved_work_items[0].lease_expires_at is None
    assert result.saved_work_items[0].last_error_kind == "resume_released_lease"
    assert unit_of_work.saved_work_items == list(result.saved_work_items)
    assert unit_of_work.committed is True


def test_resume_completed_artifact_still_prevents_leased_work_item_reactivation() -> (
    None
):
    leased = _leased_claim_extraction_work_item("unit-1")
    unit_of_work = FakeWorkItemUnitOfWork()

    result = ResumeClaimExtractionStage(
        reader=FakeResumeReader(
            artifacts=(_completed_artifact("unit-1"),),
            work_items=(leased,),
        ),
        repository=unit_of_work,
    ).execute(
        ResumeClaimExtractionStageCommand(
            workflow_run_id="workflow-1",
            stage_run_id="stage-1",
            source_units=(_source_unit("unit-1"),),
            prompt_id="faq_claim_observations",
            now=_now(),
        ),
    )

    assert result.summary.completed_count == 1
    assert result.summary.ready_count == 0
    assert result.summary.recreated_count == 0
    assert result.saved_work_items == ()
    assert unit_of_work.saved_work_items == []
    assert unit_of_work.committed is False


def test_cancel_user_action_required_uses_shared_state_machine_path() -> None:
    user_action_item = WorkItem(
        work_item_id="user-action-1",
        work_kind=WorkKind("knowledge_workbench.claim_extraction"),
        status=WorkItemStatus.USER_ACTION_REQUIRED,
        attempt_count=3,
        last_error_kind="daily_limit_exhausted",
    )
    unit_of_work = FakeCancelUnitOfWork()

    result = CancelClaimExtractionStage(
        reader=FakeCancelReader(work_items=(user_action_item,)),
        repository=unit_of_work,
    ).execute(
        CancelClaimExtractionStageCommand(
            workflow_run_id="workflow-1",
            stage_run_id="stage-1",
            reason="cancelled_by_user",
            cancelled_by="manager-1",
            occurred_at=_now(),
        ),
    )

    assert len(result.cancelled_work_items) == 1
    cancelled = result.cancelled_work_items[0]
    assert cancelled == WorkItemStateMachine.cancel(
        user_action_item,
        error_kind="cancelled_by_user",
    )
    assert cancelled.status is WorkItemStatus.CANCELLED
    assert cancelled.work_item_id == user_action_item.work_item_id
    assert cancelled.work_kind == user_action_item.work_kind
    assert cancelled.attempt_count == user_action_item.attempt_count
    assert cancelled.last_error_kind == "cancelled_by_user"
    assert unit_of_work.saved_work_items == [cancelled]
    assert unit_of_work.committed is True


def test_cancel_use_case_does_not_manually_construct_user_action_work_item() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/extraction/application/use_cases/"
        "cancel_claim_extraction_stage.py",
    ).read_text(encoding="utf-8")

    assert "if item.status is WorkItemStatus.USER_ACTION_REQUIRED" not in source
    assert "return WorkItem(" not in source
    assert "WorkItemStateMachine.cancel" in source
