from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.wait_until import WaitUntil
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.worker_ref import WorkerRef
from src.contexts.knowledge_workbench.extraction.application.read_models.claim_extraction_stage_progress import (
    ClaimExtractionStageBlockerKind,
    ClaimExtractionStageBlockerReason,
    ClaimExtractionStageNextAction,
    ClaimExtractionStageProgressQuery,
    ClaimExtractionStageProgressReadModel,
    ClaimExtractionStageProgressStatus,
)
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind


@dataclass(slots=True)
class FakeClaimExtractionStageProgressQueryPort:
    work_items: tuple[WorkItem, ...]
    artifacts_count: int = 0
    work_item_queries: list[tuple[str, str]] = field(default_factory=list)
    artifact_queries: list[tuple[str, str]] = field(default_factory=list)

    def load_work_items(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
    ) -> tuple[WorkItem, ...]:
        self.work_item_queries.append((workflow_run_id, stage_run_id))
        return self.work_items

    def count_artifacts(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
    ) -> int:
        self.artifact_queries.append((workflow_run_id, stage_run_id))
        return self.artifacts_count


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _error_kind_value(error_kind: LlmErrorKind | str | None) -> str | None:
    if isinstance(error_kind, LlmErrorKind):
        return error_kind.value
    return error_kind


def _work_item(
    item_id: str,
    *,
    status: WorkItemStatus,
    wait_seconds: int | None = None,
    error_kind: LlmErrorKind | str | None = None,
) -> WorkItem:
    if status is WorkItemStatus.LEASED:
        return WorkItem(
            work_item_id=item_id,
            work_kind=WorkKind("knowledge_workbench.claim_extraction"),
            status=status,
            leased_by=WorkerRef("worker-1"),
            lease_token=LeaseToken("lease-1"),
            lease_expires_at=_now() + timedelta(minutes=5),
        )

    if status in {WorkItemStatus.DEFERRED, WorkItemStatus.RETRYABLE_FAILED}:
        return WorkItem(
            work_item_id=item_id,
            work_kind=WorkKind("knowledge_workbench.claim_extraction"),
            status=status,
            next_attempt_at=WaitUntil(_now() + timedelta(seconds=wait_seconds or 60)),
            last_error_kind=_error_kind_value(error_kind or LlmErrorKind.MINUTE_LIMIT),
        )

    if status is WorkItemStatus.TERMINAL_FAILED:
        return WorkItem(
            work_item_id=item_id,
            work_kind=WorkKind("knowledge_workbench.claim_extraction"),
            status=status,
            last_error_kind=_error_kind_value(
                error_kind or LlmErrorKind.VALIDATION_FAILED,
            ),
        )

    if status is WorkItemStatus.CANCELLED:
        return WorkItem(
            work_item_id=item_id,
            work_kind=WorkKind("knowledge_workbench.claim_extraction"),
            status=status,
            last_error_kind=_error_kind_value(error_kind or "cancelled"),
        )

    if status is WorkItemStatus.USER_ACTION_REQUIRED:
        return WorkItem(
            work_item_id=item_id,
            work_kind=WorkKind("knowledge_workbench.claim_extraction"),
            status=status,
            last_error_kind=_error_kind_value(error_kind or LlmErrorKind.DAILY_LIMIT),
        )

    return WorkItem(
        work_item_id=item_id,
        work_kind=WorkKind("knowledge_workbench.claim_extraction"),
        status=status,
    )


def _waiting_work_item_with_raw_error(
    item_id: str,
    *,
    status: WorkItemStatus,
    wait_seconds: int | None = None,
    last_error_kind: str | None,
) -> WorkItem:
    if status not in {WorkItemStatus.DEFERRED, WorkItemStatus.RETRYABLE_FAILED}:
        raise ValueError("status must be DEFERRED or RETRYABLE_FAILED")
    return WorkItem(
        work_item_id=item_id,
        work_kind=WorkKind("knowledge_workbench.claim_extraction"),
        status=status,
        next_attempt_at=WaitUntil(_now() + timedelta(seconds=wait_seconds or 60)),
        last_error_kind=last_error_kind,
    )


def _query() -> ClaimExtractionStageProgressQuery:
    return ClaimExtractionStageProgressQuery(
        workflow_run_id="workflow-1",
        stage_run_id="stage-1",
    )


def _progress(
    work_items: tuple[WorkItem, ...],
    *,
    artifacts_count: int = 0,
):
    query_port = FakeClaimExtractionStageProgressQueryPort(
        work_items=work_items,
        artifacts_count=artifacts_count,
    )
    progress = ClaimExtractionStageProgressReadModel(query_port=query_port).execute(
        _query(),
    )
    return progress, query_port


def test_all_completed_stage_is_completed() -> None:
    progress, query_port = _progress(
        (
            _work_item("completed-1", status=WorkItemStatus.COMPLETED),
            _work_item("split-1", status=WorkItemStatus.SPLIT_SUPERSEDED),
        ),
        artifacts_count=2,
    )

    assert progress.status is ClaimExtractionStageProgressStatus.COMPLETED
    assert progress.completed_count == 1
    assert progress.split_superseded_count == 1
    assert progress.artifacts_count == 2
    assert progress.blocker_kind is None
    assert progress.blocker_reason is None
    assert progress.next_action is None
    assert query_port.work_item_queries == [("workflow-1", "stage-1")]
    assert query_port.artifact_queries == [("workflow-1", "stage-1")]


def test_deferred_minute_limit_wait_stage_has_quota_blocker_reason() -> None:
    progress, _query_port = _progress(
        (
            _work_item(
                "deferred-1",
                status=WorkItemStatus.DEFERRED,
                wait_seconds=120,
                error_kind=LlmErrorKind.MINUTE_LIMIT,
            ),
        ),
    )

    assert progress.status is ClaimExtractionStageProgressStatus.WAITING
    assert progress.status is not ClaimExtractionStageProgressStatus.WAITING_FOR_QUOTA
    assert progress.deferred_count == 1
    assert progress.nearest_wait_until == _now() + timedelta(seconds=120)
    assert progress.resume_after == _now() + timedelta(seconds=120)
    assert progress.blocker_kind is ClaimExtractionStageBlockerKind.QUOTA_WAIT
    assert (
        progress.blocker_reason
        is ClaimExtractionStageBlockerReason.WAITING_FOR_MINUTE_QUOTA
    )
    assert progress.next_action is ClaimExtractionStageNextAction.RESUME_AFTER_WAIT


def test_deferred_network_error_wait_stage_has_retry_blocker_not_quota() -> None:
    progress, _query_port = _progress(
        (
            _work_item(
                "deferred-1",
                status=WorkItemStatus.DEFERRED,
                wait_seconds=60,
                error_kind=LlmErrorKind.NETWORK_ERROR,
            ),
        ),
    )

    assert progress.status is ClaimExtractionStageProgressStatus.WAITING
    assert progress.status is not ClaimExtractionStageProgressStatus.WAITING_FOR_QUOTA
    assert progress.blocker_kind is ClaimExtractionStageBlockerKind.RETRY_WAIT
    assert (
        progress.blocker_reason
        is ClaimExtractionStageBlockerReason.NETWORK_RETRY_SCHEDULED
    )
    assert progress.next_action is ClaimExtractionStageNextAction.RETRY_WHEN_DUE


def test_retryable_invalid_output_wait_stage_has_invalid_output_retry_reason() -> None:
    progress, _query_port = _progress(
        (
            _work_item(
                "retryable-1",
                status=WorkItemStatus.RETRYABLE_FAILED,
                wait_seconds=60,
                error_kind=LlmErrorKind.INVALID_OUTPUT,
            ),
        ),
    )

    assert progress.status is ClaimExtractionStageProgressStatus.WAITING
    assert progress.retryable_failed_count == 1
    assert progress.blocker_kind is ClaimExtractionStageBlockerKind.RETRY_WAIT
    assert (
        progress.blocker_reason
        is ClaimExtractionStageBlockerReason.INVALID_OUTPUT_RETRY_SCHEDULED
    )
    assert progress.next_action is ClaimExtractionStageNextAction.RETRY_WHEN_DUE


def test_deferred_request_too_large_wait_stage_requires_source_unit_split() -> None:
    progress, _query_port = _progress(
        (
            _work_item(
                "deferred-too-large-1",
                status=WorkItemStatus.DEFERRED,
                wait_seconds=60,
                error_kind=LlmErrorKind.REQUEST_TOO_LARGE,
            ),
        ),
    )

    assert progress.status is ClaimExtractionStageProgressStatus.WAITING
    assert progress.status is not ClaimExtractionStageProgressStatus.WAITING_FOR_QUOTA
    assert progress.blocker_kind is ClaimExtractionStageBlockerKind.SPLIT_REQUIRED
    assert (
        progress.blocker_reason
        is ClaimExtractionStageBlockerReason.SOURCE_UNIT_SPLIT_REQUIRED
    )
    assert progress.next_action is ClaimExtractionStageNextAction.SPLIT_SOURCE_UNIT


@pytest.mark.parametrize("last_error_kind", ("provider_sneezed", None))
def test_unknown_or_missing_wait_reason_defaults_to_provider_retry(
    last_error_kind: str | None,
) -> None:
    progress, _query_port = _progress(
        (
            _waiting_work_item_with_raw_error(
                "deferred-unknown-1",
                status=WorkItemStatus.DEFERRED,
                wait_seconds=60,
                last_error_kind=last_error_kind,
            ),
        ),
    )

    assert progress.status is ClaimExtractionStageProgressStatus.WAITING
    assert progress.status is not ClaimExtractionStageProgressStatus.WAITING_FOR_QUOTA
    assert progress.blocker_kind is ClaimExtractionStageBlockerKind.RETRY_WAIT
    assert (
        progress.blocker_reason
        is ClaimExtractionStageBlockerReason.PROVIDER_RETRY_SCHEDULED
    )
    assert progress.next_action is ClaimExtractionStageNextAction.RETRY_WHEN_DUE


def test_deferred_and_retryable_without_quota_reason_never_collapse_to_quota() -> None:
    progress, _query_port = _progress(
        (
            _work_item(
                "deferred-network-1",
                status=WorkItemStatus.DEFERRED,
                wait_seconds=60,
                error_kind=LlmErrorKind.NETWORK_ERROR,
            ),
            _work_item(
                "retryable-invalid-1",
                status=WorkItemStatus.RETRYABLE_FAILED,
                wait_seconds=120,
                error_kind=LlmErrorKind.INVALID_OUTPUT,
            ),
        ),
    )

    assert progress.status is ClaimExtractionStageProgressStatus.WAITING
    assert progress.status is not ClaimExtractionStageProgressStatus.WAITING_FOR_QUOTA
    assert progress.blocker_kind is ClaimExtractionStageBlockerKind.RETRY_WAIT
    assert progress.blocker_kind is not ClaimExtractionStageBlockerKind.QUOTA_WAIT
    assert (
        progress.blocker_reason
        is ClaimExtractionStageBlockerReason.NETWORK_RETRY_SCHEDULED
    )
    assert progress.next_action is ClaimExtractionStageNextAction.RETRY_WHEN_DUE


def test_active_leased_stage_is_in_progress() -> None:
    progress, _query_port = _progress(
        (
            _work_item("leased-1", status=WorkItemStatus.LEASED),
            _work_item("ready-1", status=WorkItemStatus.READY),
        ),
    )

    assert progress.status is ClaimExtractionStageProgressStatus.IN_PROGRESS
    assert progress.leased_count == 1
    assert progress.ready_count == 1
    assert progress.blocker_kind is ClaimExtractionStageBlockerKind.ACTIVE_LEASE
    assert progress.blocker_reason is None
    assert progress.next_action is ClaimExtractionStageNextAction.WAIT_FOR_ACTIVE_LEASE


def test_terminal_failed_stage_is_failed_with_terminal_blocker_reason() -> None:
    progress, _query_port = _progress(
        (
            _work_item(
                "failed-1",
                status=WorkItemStatus.TERMINAL_FAILED,
                error_kind=LlmErrorKind.VALIDATION_FAILED,
            ),
            _work_item("ready-1", status=WorkItemStatus.READY),
        ),
    )

    assert progress.status is ClaimExtractionStageProgressStatus.FAILED
    assert progress.terminal_failed_count == 1
    assert progress.blocker_kind is ClaimExtractionStageBlockerKind.TERMINAL_FAILED
    assert progress.blocker_reason is ClaimExtractionStageBlockerReason.TERMINAL_FAILURE
    assert (
        progress.next_action is ClaimExtractionStageNextAction.INSPECT_TERMINAL_FAILURE
    )


def test_user_action_required_daily_limit_has_daily_choice_blocker_reason() -> None:
    progress, _query_port = _progress(
        (
            _work_item(
                "daily-limit-1",
                status=WorkItemStatus.USER_ACTION_REQUIRED,
                error_kind=LlmErrorKind.DAILY_LIMIT,
            ),
            _work_item("ready-1", status=WorkItemStatus.READY),
        ),
    )

    assert progress.status is ClaimExtractionStageProgressStatus.USER_ACTION_REQUIRED
    assert progress.user_action_required_count == 1
    assert progress.blocker_kind is ClaimExtractionStageBlockerKind.USER_ACTION_REQUIRED
    assert (
        progress.blocker_reason
        is ClaimExtractionStageBlockerReason.DAILY_LIMIT_REQUIRES_USER_CHOICE
    )
    assert (
        progress.next_action
        is ClaimExtractionStageNextAction.CHOOSE_DAILY_LIMIT_RECOVERY
    )


def test_user_action_required_non_daily_requires_failure_inspection() -> None:
    progress, _query_port = _progress(
        (
            _work_item(
                "user-action-1",
                status=WorkItemStatus.USER_ACTION_REQUIRED,
                error_kind=LlmErrorKind.AUTH_ERROR,
            ),
        ),
    )

    assert progress.status is ClaimExtractionStageProgressStatus.USER_ACTION_REQUIRED
    assert progress.blocker_kind is ClaimExtractionStageBlockerKind.USER_ACTION_REQUIRED
    assert progress.blocker_reason is ClaimExtractionStageBlockerReason.TERMINAL_FAILURE
    assert (
        progress.next_action is ClaimExtractionStageNextAction.INSPECT_TERMINAL_FAILURE
    )


def test_split_superseded_stage_does_not_imply_quota() -> None:
    progress, _query_port = _progress(
        (_work_item("split-1", status=WorkItemStatus.SPLIT_SUPERSEDED),),
    )

    assert progress.status is ClaimExtractionStageProgressStatus.COMPLETED
    assert progress.split_superseded_count == 1
    assert progress.blocker_kind is None
    assert progress.blocker_reason is None
    assert progress.next_action is None


def test_cancelled_and_partial_cancelled_statuses_are_distinct() -> None:
    cancelled, _query_port = _progress(
        (
            _work_item("cancelled-1", status=WorkItemStatus.CANCELLED),
            _work_item("cancelled-2", status=WorkItemStatus.CANCELLED),
        ),
    )
    partial, _query_port = _progress(
        (
            _work_item("cancelled-1", status=WorkItemStatus.CANCELLED),
            _work_item("ready-1", status=WorkItemStatus.READY),
        ),
    )

    assert cancelled.status is ClaimExtractionStageProgressStatus.CANCELLED
    assert cancelled.cancelled_count == 2
    assert cancelled.blocker_kind is ClaimExtractionStageBlockerKind.CANCELLED
    assert cancelled.blocker_reason is ClaimExtractionStageBlockerReason.CANCELLED
    assert cancelled.next_action is ClaimExtractionStageNextAction.STOPPED_CANCELLED
    assert partial.status is ClaimExtractionStageProgressStatus.PARTIAL_CANCELLED
    assert partial.cancelled_count == 1


def test_progress_query_rejects_empty_refs_and_negative_artifact_count() -> None:
    with pytest.raises(ValueError, match="workflow_run_id must be non-empty"):
        ClaimExtractionStageProgressQuery(workflow_run_id="", stage_run_id="stage-1")

    query_port = FakeClaimExtractionStageProgressQueryPort(
        work_items=(),
        artifacts_count=-1,
    )
    with pytest.raises(ValueError, match="artifacts_count must be >= 0"):
        ClaimExtractionStageProgressReadModel(query_port=query_port).execute(_query())


def test_progress_source_does_not_import_legacy_progress_sql_http_or_frontend() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/extraction/application/read_models/"
        "claim_extraction_stage_progress.py",
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
        "asyncpg",
        "connection.execute",
        "fetchrow",
        "fastapi",
        "APIRouter",
        "router.",
        "HTTPException",
        "src.contexts.llm_runtime.infrastructure",
        "Groq",
        "groq",
        "type: ignore",
    )

    offenders = [marker for marker in forbidden if marker in source]
    assert not offenders
