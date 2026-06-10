from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

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
from src.contexts.execution_runtime.domain.events.work_item_events import WorkItemFailed
from src.contexts.execution_runtime.domain.state_machines.work_item_state_machine import (
    WorkItemStateMachine,
)
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.wait_until import WaitUntil
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.knowledge_workbench.extraction.application.ports.claim_extraction_work_item_unit_of_work_port import (
    ClaimExtractionRuntimeEvent,
)
from src.contexts.knowledge_workbench.extraction.application.process_managers.record_claim_extraction_failed import (
    ClaimExtractionFailureMode,
    RecordClaimExtractionFailed,
    RecordClaimExtractionFailedCommand,
)
from src.contexts.llm_runtime.domain.entities.llm_attempt import LlmAttempt
from src.contexts.llm_runtime.domain.entities.llm_task import LlmTask
from src.contexts.llm_runtime.domain.events.llm_task_events import LlmTaskFailed
from src.contexts.llm_runtime.domain.value_objects.input_ref import LlmInputRef
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind
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


@dataclass(slots=True)
class FakeClaimExtractionWorkItemUnitOfWork:
    saved_work_items: list[WorkItem] = field(default_factory=list)
    saved_work_item_attempts: list[WorkItemAttempt] = field(default_factory=list)
    saved_llm_tasks: list[LlmTask] = field(default_factory=list)
    saved_llm_attempts: list[LlmAttempt] = field(default_factory=list)
    saved_artifacts: list[PipelineArtifact] = field(default_factory=list)
    appended_events: list[ClaimExtractionRuntimeEvent] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    fail_on_commit: bool = False

    def save_work_item(self, item: WorkItem) -> None:
        self.actions.append("save_work_item")
        self.saved_work_items.append(item)

    def save_work_item_attempt(self, attempt: WorkItemAttempt) -> None:
        self.actions.append("save_work_item_attempt")
        self.saved_work_item_attempts.append(attempt)

    def save_llm_task(self, task: LlmTask) -> None:
        self.actions.append("save_llm_task")
        self.saved_llm_tasks.append(task)

    def save_llm_attempt(self, attempt: LlmAttempt) -> None:
        self.actions.append("save_llm_attempt")
        self.saved_llm_attempts.append(attempt)

    def save_artifact(self, artifact: PipelineArtifact) -> None:
        self.actions.append("save_artifact")
        self.saved_artifacts.append(artifact)

    def append_event(self, event: ClaimExtractionRuntimeEvent) -> None:
        self.actions.append("append_event")
        self.appended_events.append(event)

    def commit(self) -> None:
        self.actions.append("commit")
        if self.fail_on_commit:
            raise RuntimeError("commit failed")
        self.committed = True

    def rollback(self) -> None:
        self.actions.append("rollback")
        self.rolled_back = True


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _route() -> LlmRoute:
    return LlmRoute(
        provider_id=ProviderId("provider"),
        model_id=ModelId("model"),
        account_ref=ProviderAccountRef("account"),
    )


def _leased_work_item() -> WorkItem:
    now = _now()
    return WorkItemStateMachine.lease_ready(
        WorkItem(
            work_item_id="work-1",
            work_kind=WorkKind("knowledge_workbench.claim_extraction"),
        ),
        worker=WorkerRef("worker-1"),
        lease_token=LeaseToken("lease-1"),
        lease_expires_at=now + timedelta(seconds=30),
        now=now,
    )


def _work_item_attempt(
    error_kind: LlmErrorKind = LlmErrorKind.VALIDATION_FAILED,
) -> WorkItemAttempt:
    return WorkItemAttempt(
        attempt_id="work-attempt-1",
        work_item_id="work-1",
        attempt_number=1,
        started_at=_now(),
        finished_at=_now(),
        outcome_status="failed",
        error_kind=error_kind.value,
    )


def _llm_task(
    *,
    status: LlmTaskStatus,
    error_kind: LlmErrorKind = LlmErrorKind.VALIDATION_FAILED,
) -> LlmTask:
    return LlmTask(
        task_id="llm-task-1",
        prompt_id="faq_claim_observations",
        prompt_version=PromptVersion("v1"),
        input_ref=LlmInputRef("source-unit-1"),
        output_contract_ref=OutputContractRef("claim_observations_json_v1"),
        status=status,
        selected_route=_route(),
        last_error_kind=error_kind,
    )


def _llm_attempt(
    error_kind: LlmErrorKind = LlmErrorKind.VALIDATION_FAILED,
) -> LlmAttempt:
    return LlmAttempt(
        attempt_id="llm-attempt-1",
        task_id="llm-task-1",
        attempt_number=1,
        route=_route(),
        started_at=_now(),
        finished_at=_now(),
        error_kind=error_kind,
    )


def _error_artifact(
    error_kind: LlmErrorKind = LlmErrorKind.VALIDATION_FAILED,
) -> PipelineArtifact:
    return PipelineArtifact(
        artifact_ref=ArtifactRef("error-artifact-1"),
        artifact_kind=ArtifactKind("knowledge_workbench.claim_observations.error"),
        payload=ArtifactPayload({"error_kind": error_kind.value}),
        status=ArtifactStatus.STORED,
        visibility=ArtifactVisibility.INTERNAL,
        retention_policy=RetentionPolicy.temporary(),
        lineage=ArtifactLineage(),
        created_at=_now(),
        updated_at=_now(),
    )


def _retryable_command(
    *,
    error_artifact: PipelineArtifact | None = None,
) -> RecordClaimExtractionFailedCommand:
    return RecordClaimExtractionFailedCommand(
        leased_work_item=_leased_work_item(),
        work_item_attempt=_work_item_attempt(),
        llm_task=_llm_task(status=LlmTaskStatus.RETRYABLE_FAILED),
        llm_attempt=_llm_attempt(),
        mode=ClaimExtractionFailureMode.RETRYABLE,
        next_attempt_at=WaitUntil(_now() + timedelta(seconds=30)),
        error_artifact=error_artifact,
        occurred_at=_now(),
    )


def _terminal_command(
    *,
    error_artifact: PipelineArtifact | None = None,
) -> RecordClaimExtractionFailedCommand:
    return RecordClaimExtractionFailedCommand(
        leased_work_item=_leased_work_item(),
        work_item_attempt=_work_item_attempt(error_kind=LlmErrorKind.AUTH_ERROR),
        llm_task=_llm_task(
            status=LlmTaskStatus.TERMINAL_FAILED,
            error_kind=LlmErrorKind.AUTH_ERROR,
        ),
        llm_attempt=_llm_attempt(error_kind=LlmErrorKind.AUTH_ERROR),
        mode=ClaimExtractionFailureMode.TERMINAL,
        error_artifact=error_artifact,
        occurred_at=_now(),
    )


def test_record_claim_extraction_failed_commits_retryable_failure() -> None:
    unit_of_work = FakeClaimExtractionWorkItemUnitOfWork()

    result = RecordClaimExtractionFailed(repository=unit_of_work).execute(
        _retryable_command(),
    )

    assert result.failed_work_item.status is WorkItemStatus.RETRYABLE_FAILED
    assert result.failed_work_item.next_attempt_at == WaitUntil(
        _now() + timedelta(seconds=30),
    )
    assert (
        result.failed_work_item.last_error_kind == LlmErrorKind.VALIDATION_FAILED.value
    )
    assert result.failed_work_item.leased_by is None
    assert result.failed_work_item.lease_token is None

    assert isinstance(result.work_item_event, WorkItemFailed)
    assert result.work_item_event.status is WorkItemStatus.RETRYABLE_FAILED
    assert result.work_item_event.error_kind == LlmErrorKind.VALIDATION_FAILED.value

    assert isinstance(result.llm_event, LlmTaskFailed)
    assert result.llm_event.error_kind is LlmErrorKind.VALIDATION_FAILED

    assert unit_of_work.saved_work_items == [result.failed_work_item]
    assert unit_of_work.saved_llm_tasks == [
        _llm_task(status=LlmTaskStatus.RETRYABLE_FAILED),
    ]
    assert unit_of_work.saved_artifacts == []
    assert unit_of_work.appended_events == [
        result.work_item_event,
        result.llm_event,
    ]
    assert unit_of_work.committed
    assert not unit_of_work.rolled_back


def test_record_claim_extraction_failed_commits_terminal_failure() -> None:
    unit_of_work = FakeClaimExtractionWorkItemUnitOfWork()

    result = RecordClaimExtractionFailed(repository=unit_of_work).execute(
        _terminal_command(),
    )

    assert result.failed_work_item.status is WorkItemStatus.TERMINAL_FAILED
    assert result.failed_work_item.next_attempt_at is None
    assert result.failed_work_item.last_error_kind == LlmErrorKind.AUTH_ERROR.value
    assert isinstance(result.work_item_event, WorkItemFailed)
    assert result.work_item_event.status is WorkItemStatus.TERMINAL_FAILED
    assert isinstance(result.llm_event, LlmTaskFailed)
    assert result.llm_event.error_kind is LlmErrorKind.AUTH_ERROR
    assert unit_of_work.committed


def test_record_claim_extraction_failed_can_store_error_artifact() -> None:
    unit_of_work = FakeClaimExtractionWorkItemUnitOfWork()
    error_artifact = _error_artifact()

    result = RecordClaimExtractionFailed(repository=unit_of_work).execute(
        _retryable_command(error_artifact=error_artifact),
    )

    assert result.error_artifact_event is not None
    assert isinstance(result.error_artifact_event, ArtifactStored)
    assert unit_of_work.saved_artifacts == [error_artifact]
    assert unit_of_work.appended_events == [
        result.work_item_event,
        result.llm_event,
        result.error_artifact_event,
    ]


def test_record_claim_extraction_failed_rolls_back_when_commit_fails() -> None:
    unit_of_work = FakeClaimExtractionWorkItemUnitOfWork(fail_on_commit=True)

    with pytest.raises(RuntimeError, match="commit failed"):
        RecordClaimExtractionFailed(repository=unit_of_work).execute(
            _retryable_command(),
        )

    assert not unit_of_work.committed
    assert unit_of_work.rolled_back
    assert unit_of_work.actions[-2:] == ["commit", "rollback"]


def test_record_claim_extraction_failed_rejects_mismatched_retryable_task() -> None:
    with pytest.raises(ValueError):
        RecordClaimExtractionFailedCommand(
            leased_work_item=_leased_work_item(),
            work_item_attempt=_work_item_attempt(),
            llm_task=_llm_task(status=LlmTaskStatus.TERMINAL_FAILED),
            llm_attempt=_llm_attempt(),
            mode=ClaimExtractionFailureMode.RETRYABLE,
            next_attempt_at=WaitUntil(_now() + timedelta(seconds=30)),
            occurred_at=_now(),
        )


def test_record_claim_extraction_failed_rejects_mismatched_terminal_task() -> None:
    with pytest.raises(ValueError):
        RecordClaimExtractionFailedCommand(
            leased_work_item=_leased_work_item(),
            work_item_attempt=_work_item_attempt(),
            llm_task=_llm_task(status=LlmTaskStatus.RETRYABLE_FAILED),
            llm_attempt=_llm_attempt(),
            mode=ClaimExtractionFailureMode.TERMINAL,
            occurred_at=_now(),
        )


def test_record_claim_extraction_failed_requires_retry_wait_for_retryable_mode() -> (
    None
):
    with pytest.raises(ValueError):
        RecordClaimExtractionFailedCommand(
            leased_work_item=_leased_work_item(),
            work_item_attempt=_work_item_attempt(),
            llm_task=_llm_task(status=LlmTaskStatus.RETRYABLE_FAILED),
            llm_attempt=_llm_attempt(),
            mode=ClaimExtractionFailureMode.RETRYABLE,
            occurred_at=_now(),
        )


def test_record_claim_extraction_failed_requires_timezone_aware_occurred_at() -> None:
    with pytest.raises(ValueError):
        RecordClaimExtractionFailedCommand(
            leased_work_item=_leased_work_item(),
            work_item_attempt=_work_item_attempt(),
            llm_task=_llm_task(status=LlmTaskStatus.RETRYABLE_FAILED),
            llm_attempt=_llm_attempt(),
            mode=ClaimExtractionFailureMode.RETRYABLE,
            next_attempt_at=WaitUntil(_now() + timedelta(seconds=30)),
            occurred_at=datetime(2026, 6, 8, 12, 0),
        )
