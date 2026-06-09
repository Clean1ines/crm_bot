from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.wait_until import WaitUntil
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.extraction.application.read_models import (
    claim_extraction_stage_progress_async as async_progress_module,
)
from src.contexts.knowledge_workbench.extraction.application.read_models.claim_extraction_stage_progress import (
    ClaimExtractionStageBlockerKind,
    ClaimExtractionStageBlockerReason,
    ClaimExtractionStageNextAction,
    ClaimExtractionStageProgress,
    ClaimExtractionStageProgressQuery,
    ClaimExtractionStageProgressStatus,
)
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind


@dataclass(slots=True)
class FakeAsyncClaimExtractionStageProgressQueryPort:
    work_items: tuple[WorkItem, ...]
    artifacts_count: int = 0
    work_item_queries: list[tuple[str, str]] = field(default_factory=list)
    artifact_queries: list[tuple[str, str]] = field(default_factory=list)

    async def load_work_items(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
    ) -> tuple[WorkItem, ...]:
        self.work_item_queries.append((workflow_run_id, stage_run_id))
        return self.work_items

    async def count_artifacts(
        self,
        *,
        workflow_run_id: str,
        stage_run_id: str,
    ) -> int:
        self.artifact_queries.append((workflow_run_id, stage_run_id))
        return self.artifacts_count


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _query() -> ClaimExtractionStageProgressQuery:
    return ClaimExtractionStageProgressQuery(
        workflow_run_id="workflow-1",
        stage_run_id="stage-1",
    )


def _deferred_network_work_item() -> WorkItem:
    return WorkItem(
        work_item_id="deferred-network-1",
        work_kind=WorkKind("knowledge_workbench.claim_extraction"),
        status=WorkItemStatus.DEFERRED,
        next_attempt_at=WaitUntil(_now() + timedelta(seconds=60)),
        last_error_kind=LlmErrorKind.NETWORK_ERROR.value,
    )


def test_async_progress_read_model_delegates_to_sync_canonical_mapping(
    monkeypatch,
) -> None:
    work_items = (_deferred_network_work_item(),)
    query = _query()
    async_query_port = FakeAsyncClaimExtractionStageProgressQueryPort(
        work_items=work_items,
        artifacts_count=3,
    )
    delegated: dict[str, object] = {}

    class SpyCanonicalProgressReadModel:
        def __init__(self, *, query_port: object) -> None:
            self._query_port = query_port
            delegated["query_port_type"] = type(query_port).__name__

        def execute(
            self,
            query: ClaimExtractionStageProgressQuery,
        ) -> ClaimExtractionStageProgress:
            delegated["query"] = query
            delegated["work_items"] = self._query_port.load_work_items(
                workflow_run_id=query.workflow_run_id,
                stage_run_id=query.stage_run_id,
            )
            delegated["artifacts_count"] = self._query_port.count_artifacts(
                workflow_run_id=query.workflow_run_id,
                stage_run_id=query.stage_run_id,
            )
            return ClaimExtractionStageProgress(
                status=ClaimExtractionStageProgressStatus.WAITING,
                ready_count=0,
                leased_count=0,
                deferred_count=1,
                completed_count=0,
                retryable_failed_count=0,
                terminal_failed_count=0,
                cancelled_count=0,
                split_superseded_count=0,
                artifacts_count=3,
                nearest_wait_until=_now() + timedelta(seconds=60),
                blocker_kind=ClaimExtractionStageBlockerKind.RETRY_WAIT,
                blocker_reason=(
                    ClaimExtractionStageBlockerReason.NETWORK_RETRY_SCHEDULED
                ),
                next_action=ClaimExtractionStageNextAction.RETRY_WHEN_DUE,
                user_action_required_count=0,
            )

    monkeypatch.setattr(
        async_progress_module,
        "ClaimExtractionStageProgressReadModel",
        SpyCanonicalProgressReadModel,
    )

    progress = asyncio.run(
        async_progress_module.AsyncClaimExtractionStageProgressReadModel(
            query_port=async_query_port,
        ).execute(query),
    )

    assert async_query_port.work_item_queries == [("workflow-1", "stage-1")]
    assert async_query_port.artifact_queries == [("workflow-1", "stage-1")]
    assert delegated["query"] == query
    assert delegated["work_items"] == work_items
    assert delegated["artifacts_count"] == 3
    assert (
        delegated["query_port_type"] == "_LoadedClaimExtractionStageProgressQueryPort"
    )

    assert progress.status is ClaimExtractionStageProgressStatus.WAITING
    assert progress.blocker_kind is ClaimExtractionStageBlockerKind.RETRY_WAIT
    assert (
        progress.blocker_reason
        is ClaimExtractionStageBlockerReason.NETWORK_RETRY_SCHEDULED
    )
    assert progress.next_action is ClaimExtractionStageNextAction.RETRY_WHEN_DUE


def test_async_progress_source_does_not_duplicate_blocker_reason_mapping() -> None:
    source = Path(
        "src/contexts/knowledge_workbench/extraction/application/read_models/"
        "claim_extraction_stage_progress_async.py",
    ).read_text(encoding="utf-8")

    assert "ClaimExtractionStageProgressReadModel(" in source

    forbidden_mapping_markers = (
        "WAITING_FOR_QUOTA",
        "QUOTA_WAIT",
        "ClaimExtractionStageBlockerKind",
        "ClaimExtractionStageBlockerReason",
        "ClaimExtractionStageNextAction",
        "WorkItemStatus.DEFERRED",
        "WorkItemStatus.RETRYABLE_FAILED",
        "deferred_count",
        "retryable_failed_count",
        "nearest_wait_until",
        "last_error_kind",
        "_stage_blocker_interpretation",
        "_waiting_interpretation",
    )

    offenders = [marker for marker in forbidden_mapping_markers if marker in source]
    assert not offenders
