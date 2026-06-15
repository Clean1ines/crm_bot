from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Protocol, cast

import asyncpg

from src.contexts.knowledge_workbench.observability.application.read_models.workbench_document_workflow_live_state import (
    WorkbenchCurationAvailabilityView,
    WorkbenchDocumentWorkflowLiveState,
    WorkbenchLlmAttemptLiveView,
    WorkbenchRetryTimerLiveView,
    WorkbenchSectionLaneLiveView,
    WorkbenchSectionQueueItemLiveView,
    WorkbenchWorkflowActionView,
    WorkbenchWorkflowLiveState,
    WorkbenchWorkflowModelUsageLiveView,
    WorkbenchWorkflowStageLiveView,
    WorkbenchWorkflowTimerLiveView,
    WorkbenchWorkflowUsageLiveView,
)


class WorkbenchWorkflowLiveStateNotFoundError(LookupError):
    pass


class WorkbenchWorkflowLiveStateDbPool(Protocol):
    async def acquire(self): ...


class WorkbenchWorkflowLiveStateQuery:
    def __init__(self, connection: asyncpg.Connection) -> None:
        self._connection = connection

    async def fetch_live_state(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> WorkbenchDocumentWorkflowLiveState:
        document_row = await self._document_row(
            project_id=project_id,
            document_id=document_id,
        )
        if document_row is None:
            raise WorkbenchWorkflowLiveStateNotFoundError(
                "Workbench document not found"
            )

        workflow_run_id = _optional_str(document_row, "workflow_run_id")
        processing_run_id = _optional_str(document_row, "current_processing_run_id")

        lanes = await self._section_lanes(
            project_id=project_id,
            document_id=document_id,
            processing_run_id=processing_run_id,
        )
        attempts = await self._llm_attempts(
            project_id=project_id,
            document_id=document_id,
            processing_run_id=processing_run_id,
        )
        model_summaries = await self._model_summaries(
            project_id=project_id,
            document_id=document_id,
            processing_run_id=processing_run_id,
        )
        counts = await self._counts(
            project_id=project_id,
            document_id=document_id,
            workflow_run_id=workflow_run_id,
        )
        curation = await self._curation(
            workflow_run_id=workflow_run_id,
            preview_ready=_int(counts, "preview_count") > 0,
            compacted_done=_int(counts, "active_compacted_nodes") > 0,
        )

        timer = _timer(document_row)
        usage = WorkbenchWorkflowUsageLiveView(
            total_prompt_tokens=_int(document_row, "total_prompt_tokens"),
            total_completion_tokens=_int(document_row, "total_completion_tokens"),
            total_tokens=_int(document_row, "total_tokens"),
            total_llm_calls=_int(document_row, "total_llm_calls"),
            model_summaries=model_summaries,
        )

        workflow_status = _optional_str(document_row, "workflow_status")
        current_phase = _optional_str(document_row, "current_phase")

        workflow = WorkbenchWorkflowLiveState(
            workflow_run_id=workflow_run_id,
            source_document_ref=_optional_str(document_row, "source_document_ref"),
            workflow_status=workflow_status,
            current_phase=current_phase,
            timer=timer,
            usage=usage,
            stages=_stages(
                workflow_status=workflow_status,
                current_phase=current_phase,
                document_row=document_row,
                counts=counts,
                curation=curation,
            ),
            section_lanes=lanes,
            llm_attempts=attempts,
            curation=curation,
            actions=_actions(workflow_status=workflow_status, curation=curation),
        )
        return WorkbenchDocumentWorkflowLiveState(
            document_id=_str(document_row, "document_id"),
            project_id=_str(document_row, "project_id"),
            file_name=_str(document_row, "file_name"),
            document_status=_str(document_row, "document_status"),
            current_processing_run_id=processing_run_id,
            workflow=workflow,
        )

    async def _document_row(
        self,
        *,
        project_id: str,
        document_id: str,
    ) -> Mapping[str, object] | None:
        row = await self._connection.fetchrow(
            """
            SELECT
                d.document_id,
                d.project_id::text AS project_id,
                d.file_name,
                d.status AS document_status,
                d.current_processing_run_id,
                pr.status AS processing_status,
                pr.started_at,
                pr.completed_at,
                COALESCE(pr.active_elapsed_seconds, 0) AS active_elapsed_seconds,
                COALESCE(pr.wall_elapsed_seconds, 0) AS wall_elapsed_seconds,
                pr.current_active_started_at,
                COALESCE(pr.total_prompt_tokens, 0) AS total_prompt_tokens,
                COALESCE(pr.total_completion_tokens, 0) AS total_completion_tokens,
                COALESCE(pr.total_tokens, 0) AS total_tokens,
                COALESCE(pr.total_llm_calls, 0) AS total_llm_calls,
                wf.workflow_run_id,
                wf.source_document_ref,
                wf.status AS workflow_status,
                wf.current_phase,
                wf.completed_at AS workflow_completed_at,
                wf.cancelled_at AS workflow_cancelled_at
            FROM knowledge_workbench_documents AS d
            LEFT JOIN knowledge_workbench_processing_runs AS pr
              ON pr.project_id = d.project_id
             AND pr.document_id = d.document_id
             AND pr.processing_run_id = d.current_processing_run_id
            LEFT JOIN LATERAL (
                SELECT w.*
                FROM knowledge_extraction_workflow_runs AS w
                WHERE w.project_id = d.project_id::text
                  AND w.source_document_ref = d.document_id
                ORDER BY w.updated_at DESC, w.created_at DESC
                LIMIT 1
            ) AS wf ON TRUE
            WHERE d.project_id = $1
              AND d.document_id = $2
              AND d.deleted_at IS NULL
            """,
            project_id,
            document_id,
        )
        return dict(row) if row is not None else None

    async def _section_lanes(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str | None,
    ) -> tuple[WorkbenchSectionLaneLiveView, ...]:
        rows = await self._connection.fetch(
            """
            SELECT
                queue_item_id,
                section_id,
                section_index,
                section_key,
                lane_id,
                lane_index,
                status,
                claimed_by_worker_id,
                lease_expires_at,
                error_kind,
                COALESCE(attempt_count, 0) AS attempt_count
            FROM knowledge_workbench_section_batch_queue_items
            WHERE project_id = $1
              AND document_id = $2
              AND ($3::text IS NULL OR processing_run_id = $3)
            ORDER BY lane_index ASC, section_index ASC, queue_item_id ASC
            LIMIT 500
            """,
            project_id,
            document_id,
            processing_run_id,
        )

        by_lane: dict[tuple[int, str], list[WorkbenchSectionQueueItemLiveView]] = {}
        for raw in rows:
            row = dict(raw)
            lane_key = (_int(row, "lane_index"), _str(row, "lane_id"))
            by_lane.setdefault(lane_key, []).append(_queue_item(row))

        lanes: list[WorkbenchSectionLaneLiveView] = []
        for lane_key, items in sorted(by_lane.items()):
            lane_index, lane_id = lane_key
            lanes.append(
                _lane(lane_index=lane_index, lane_id=lane_id, items=tuple(items))
            )
        return tuple(lanes)

    async def _llm_attempts(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str | None,
    ) -> tuple[WorkbenchLlmAttemptLiveView, ...]:
        rows = await self._connection.fetch(
            """
            SELECT
                node_run_id,
                section_id,
                node_name,
                node_kind,
                status,
                started_at,
                completed_at,
                duration_ms,
                model_provider,
                model_name,
                COALESCE(prompt_tokens, 0) AS prompt_tokens,
                COALESCE(completion_tokens, 0) AS completion_tokens,
                COALESCE(total_tokens, 0) AS total_tokens,
                error_kind,
                error_message_user
            FROM knowledge_workbench_processing_node_runs
            WHERE project_id = $1
              AND document_id = $2
              AND ($3::text IS NULL OR processing_run_id = $3)
            ORDER BY started_at DESC NULLS LAST, created_at DESC
            LIMIT 100
            """,
            project_id,
            document_id,
            processing_run_id,
        )
        return tuple(_attempt(dict(row)) for row in rows)

    async def _model_summaries(
        self,
        *,
        project_id: str,
        document_id: str,
        processing_run_id: str | None,
    ) -> tuple[WorkbenchWorkflowModelUsageLiveView, ...]:
        rows = await self._connection.fetch(
            """
            SELECT
                model_provider,
                model_name,
                COUNT(*)::int AS call_count,
                COALESCE(SUM(prompt_tokens), 0)::int AS prompt_tokens,
                COALESCE(SUM(completion_tokens), 0)::int AS completion_tokens,
                COALESCE(SUM(total_tokens), 0)::int AS total_tokens,
                COALESCE(SUM(duration_ms), 0)::int AS duration_ms_total
            FROM knowledge_workbench_processing_node_runs
            WHERE project_id = $1
              AND document_id = $2
              AND ($3::text IS NULL OR processing_run_id = $3)
              AND (model_provider IS NOT NULL OR model_name IS NOT NULL)
            GROUP BY model_provider, model_name
            ORDER BY call_count DESC, total_tokens DESC
            """,
            project_id,
            document_id,
            processing_run_id,
        )
        return tuple(
            WorkbenchWorkflowModelUsageLiveView(
                model_provider=_optional_str(dict(row), "model_provider"),
                model_name=_optional_str(dict(row), "model_name"),
                call_count=_int(dict(row), "call_count"),
                prompt_tokens=_int(dict(row), "prompt_tokens"),
                completion_tokens=_int(dict(row), "completion_tokens"),
                total_tokens=_int(dict(row), "total_tokens"),
                duration_ms_total=_int(dict(row), "duration_ms_total"),
            )
            for row in rows
        )

    async def _counts(
        self,
        *,
        project_id: str,
        document_id: str,
        workflow_run_id: str | None,
    ) -> Mapping[str, object]:
        row = await self._connection.fetchrow(
            """
            SELECT
                (
                    SELECT COUNT(*)::int
                    FROM knowledge_workbench_document_sections AS s
                    WHERE s.project_id = $1
                      AND s.document_id = $2
                ) AS source_section_count,
                (
                    SELECT COUNT(*)::int
                    FROM draft_claim_observations AS o
                    JOIN source_units AS u
                      ON u.unit_ref = o.source_unit_ref
                    WHERE u.document_ref = $2
                ) AS draft_claim_count,
                (
                    SELECT COUNT(*)::int
                    FROM draft_claim_embeddings AS e
                    WHERE e.workflow_run_id = $3
                ) AS draft_claim_embedding_count,
                (
                    SELECT COUNT(*)::int
                    FROM draft_claim_compaction_nodes AS n
                    WHERE n.workflow_run_id = $3
                      AND n.node_kind = 'compacted'
                      AND n.active IS TRUE
                ) AS active_compacted_nodes,
                (
                    SELECT COUNT(*)::int
                    FROM draft_claim_compaction_comparisons AS c
                    WHERE c.workflow_run_id = $3
                      AND c.status IN ('pending', 'waiting_user_model_choice')
                ) AS pending_compaction_comparisons,
                (
                    SELECT COUNT(*)::int
                    FROM draft_claim_cluster_previews AS p
                    WHERE p.workflow_run_id = $3
                ) AS preview_count
            """,
            project_id,
            document_id,
            workflow_run_id,
        )
        return dict(row) if row is not None else {}

    async def _curation(
        self,
        *,
        workflow_run_id: str | None,
        preview_ready: bool,
        compacted_done: bool,
    ) -> WorkbenchCurationAvailabilityView:
        if workflow_run_id is None:
            return WorkbenchCurationAvailabilityView(
                available=False,
                reason_code="workflow_missing",
                workflow_run_id=None,
                workspace_ref=None,
                workspace_status=None,
                item_count=0,
                excluded_item_count=0,
            )

        row = await self._connection.fetchrow(
            """
            SELECT
                w.workspace_ref,
                w.status AS workspace_status,
                COUNT(i.item_ref)::int AS item_count,
                COUNT(i.item_ref) FILTER (WHERE i.excluded IS TRUE)::int AS excluded_item_count
            FROM draft_claim_curation_workspaces AS w
            LEFT JOIN draft_claim_curation_items AS i
              ON i.workspace_ref = w.workspace_ref
            WHERE w.workflow_run_id = $1
            GROUP BY w.workspace_ref, w.status
            """,
            workflow_run_id,
        )
        if row is not None:
            data = dict(row)
            return WorkbenchCurationAvailabilityView(
                available=True,
                reason_code="workspace_exists",
                workflow_run_id=workflow_run_id,
                workspace_ref=_optional_str(data, "workspace_ref"),
                workspace_status=_optional_str(data, "workspace_status"),
                item_count=_int(data, "item_count"),
                excluded_item_count=_int(data, "excluded_item_count"),
            )

        available = preview_ready or compacted_done
        return WorkbenchCurationAvailabilityView(
            available=available,
            reason_code="ready_to_open" if available else "preview_not_ready",
            workflow_run_id=workflow_run_id,
            workspace_ref=None,
            workspace_status=None,
            item_count=0,
            excluded_item_count=0,
        )


async def fetch_workbench_workflow_live_state(
    *,
    pool: WorkbenchWorkflowLiveStateDbPool,
    project_id: str,
    document_id: str,
) -> dict[str, object]:
    async with cast(asyncpg.Pool, pool).acquire() as connection:
        query = WorkbenchWorkflowLiveStateQuery(cast(asyncpg.Connection, connection))
        return (
            await query.fetch_live_state(project_id=project_id, document_id=document_id)
        ).to_dict()


def _timer(row: Mapping[str, object]) -> WorkbenchWorkflowTimerLiveView:
    workflow_status = (_optional_str(row, "workflow_status") or "").upper()
    processing_status = (_optional_str(row, "processing_status") or "").lower()
    current_active_started_at = _optional_datetime(row, "current_active_started_at")
    running = (
        current_active_started_at is not None
        and workflow_status not in {"PAUSED", "FAILED", "CANCELLED", "COMPLETED"}
        and processing_status
        not in {"paused", "failed", "cancelled", "cancelled_by_user", "completed"}
    )
    if running:
        mode = "running"
    elif workflow_status == "PAUSED" or processing_status == "paused":
        mode = "paused"
    elif workflow_status == "COMPLETED" or processing_status == "completed":
        mode = "completed"
    else:
        mode = "stopped"

    return WorkbenchWorkflowTimerLiveView(
        mode=mode,
        active_elapsed_seconds=_int(row, "active_elapsed_seconds"),
        wall_elapsed_seconds=_int(row, "wall_elapsed_seconds"),
        current_active_started_at=current_active_started_at,
        started_at=_optional_datetime(row, "started_at"),
        completed_at=(
            _optional_datetime(row, "workflow_completed_at")
            or _optional_datetime(row, "completed_at")
        ),
        is_live=running,
    )


def _stages(
    *,
    workflow_status: str | None,
    current_phase: str | None,
    document_row: Mapping[str, object],
    counts: Mapping[str, object],
    curation: WorkbenchCurationAvailabilityView,
) -> tuple[WorkbenchWorkflowStageLiveView, ...]:
    source_sections = _int(counts, "source_section_count")
    draft_claim_count = _int(counts, "draft_claim_count")
    embedding_count = _int(counts, "draft_claim_embedding_count")
    compacted_count = _int(counts, "active_compacted_nodes")
    preview_count = _int(counts, "preview_count")
    status = (workflow_status or "").upper()
    phase = (current_phase or "").upper()

    return (
        WorkbenchWorkflowStageLiveView(
            id="source_ingestion",
            label="Source ingestion",
            status="completed"
            if source_sections > 0
            else _stage_pending_or_running(status),
            current=source_sections,
            total=source_sections,
            message="Source units persisted"
            if source_sections
            else "Waiting for source units",
            started_at=_optional_datetime(document_row, "started_at"),
        ),
        WorkbenchWorkflowStageLiveView(
            id="prompt_a_claim_extraction",
            label="Prompt A claim extraction",
            status=_count_stage_status(draft_claim_count, source_sections, status),
            current=draft_claim_count,
            total=source_sections,
            message="Draft claims extracted from sections",
        ),
        WorkbenchWorkflowStageLiveView(
            id="draft_claim_embeddings",
            label="Draft claim embeddings",
            status=_count_stage_status(embedding_count, draft_claim_count, status),
            current=embedding_count,
            total=draft_claim_count,
            message="Draft claim embeddings persisted",
        ),
        WorkbenchWorkflowStageLiveView(
            id="draft_claim_clustering",
            label="Draft claim clustering",
            status="completed"
            if phase
            in {
                "DRAFT_CLUSTERS_BUILT",
                "PROMPT_B_WORK_SCHEDULED",
                "PROMPT_B_WORK_COMPLETED",
                "FINAL_KNOWLEDGE_PREPARED",
                "WAITING_FOR_REVIEW",
                "REVIEW_COMPLETED",
                "PUBLISHED",
                "DONE",
            }
            else "unknown",
            current=1
            if phase
            in {
                "DRAFT_CLUSTERS_BUILT",
                "PROMPT_B_WORK_SCHEDULED",
                "PROMPT_B_WORK_COMPLETED",
                "FINAL_KNOWLEDGE_PREPARED",
                "WAITING_FOR_REVIEW",
                "REVIEW_COMPLETED",
                "PUBLISHED",
                "DONE",
            }
            else 0,
            total=1,
            message="Derived from workflow phase",
        ),
        WorkbenchWorkflowStageLiveView(
            id="draft_claim_compaction",
            label="Draft claim compaction",
            status="completed" if compacted_count > 0 else "unknown",
            current=compacted_count,
            total=compacted_count,
            message="Active compacted nodes available"
            if compacted_count
            else "No compacted nodes observed",
        ),
        WorkbenchWorkflowStageLiveView(
            id="cluster_preview",
            label="Cluster preview",
            status="completed" if preview_count > 0 else "pending",
            current=preview_count,
            total=1,
            message="Cluster preview persisted"
            if preview_count
            else "Preview not persisted yet",
        ),
        WorkbenchWorkflowStageLiveView(
            id="curation",
            label="Curation",
            status="completed"
            if curation.workspace_ref
            else ("pending" if curation.available else "unknown"),
            current=curation.item_count,
            total=curation.item_count,
            message=curation.reason_code,
        ),
        WorkbenchWorkflowStageLiveView(
            id="publication",
            label="Publication",
            status="unknown",
            current=0,
            total=0,
            message="Publication is outside this curation foundation patch",
        ),
    )


def _actions(
    *,
    workflow_status: str | None,
    curation: WorkbenchCurationAvailabilityView,
) -> tuple[WorkbenchWorkflowActionView, ...]:
    status = (workflow_status or "").upper()
    paused = status == "PAUSED"
    terminal = status in {"FAILED", "CANCELLED", "COMPLETED", "DONE"}
    return (
        WorkbenchWorkflowActionView(
            action_id="open_curation",
            visible=True,
            enabled=curation.available,
            reason_code=None if curation.available else curation.reason_code,
        ),
        WorkbenchWorkflowActionView(
            action_id="pause_processing",
            visible=True,
            enabled=not paused and not terminal,
            reason_code=None if not paused and not terminal else "not_running",
        ),
        WorkbenchWorkflowActionView(
            action_id="resume_processing",
            visible=True,
            enabled=paused,
            reason_code=None if paused else "not_paused",
        ),
        WorkbenchWorkflowActionView(
            action_id="cancel_processing",
            visible=True,
            enabled=not terminal,
            reason_code=None if not terminal else "terminal_workflow",
        ),
    )


def _queue_item(row: Mapping[str, object]) -> WorkbenchSectionQueueItemLiveView:
    lease_expires_at = _optional_datetime(row, "lease_expires_at")
    retry_seconds = None
    if lease_expires_at is not None:
        retry_seconds = max(
            0, int((lease_expires_at - datetime.now(timezone.utc)).total_seconds())
        )
    return WorkbenchSectionQueueItemLiveView(
        queue_item_id=_str(row, "queue_item_id"),
        section_id=_str(row, "section_id"),
        section_index=_int(row, "section_index"),
        section_key=_str(row, "section_key"),
        status=_str(row, "status"),
        attempt_count=_int(row, "attempt_count"),
        lease_expires_at=lease_expires_at,
        claimed_by_worker_id=_optional_str(row, "claimed_by_worker_id"),
        error_kind=_optional_str(row, "error_kind"),
        retry_timer=WorkbenchRetryTimerLiveView(
            retry_available_at=lease_expires_at,
            seconds_until_retry=retry_seconds,
        ),
    )


def _lane(
    *,
    lane_index: int,
    lane_id: str,
    items: tuple[WorkbenchSectionQueueItemLiveView, ...],
) -> WorkbenchSectionLaneLiveView:
    return WorkbenchSectionLaneLiveView(
        lane_index=lane_index,
        lane_id=lane_id,
        ready_count=sum(1 for item in items if item.status == "ready"),
        leased_count=sum(1 for item in items if item.status == "leased"),
        done_count=sum(1 for item in items if item.status in _DONE_QUEUE_STATUSES),
        failed_count=sum(1 for item in items if item.status == "failed"),
        waiting_count=sum(1 for item in items if item.status.startswith("waiting")),
        total_attempt_count=sum(item.attempt_count for item in items),
        max_attempt_count=max((item.attempt_count for item in items), default=0),
        items=items,
    )


_DONE_QUEUE_STATUSES = frozenset(
    {
        "claim_observations_persisted",
        "registry_application_queued",
        "registry_application_applied",
        "waiting_for_fresh_registry",
    }
)


def _attempt(row: Mapping[str, object]) -> WorkbenchLlmAttemptLiveView:
    return WorkbenchLlmAttemptLiveView(
        node_run_id=_str(row, "node_run_id"),
        section_id=_optional_str(row, "section_id"),
        node_name=_str(row, "node_name"),
        node_kind=_str(row, "node_kind"),
        status=_str(row, "status"),
        started_at=_optional_datetime(row, "started_at"),
        completed_at=_optional_datetime(row, "completed_at"),
        duration_ms=_optional_int(row, "duration_ms"),
        model_provider=_optional_str(row, "model_provider"),
        model_name=_optional_str(row, "model_name"),
        prompt_tokens=_int(row, "prompt_tokens"),
        completion_tokens=_int(row, "completion_tokens"),
        total_tokens=_int(row, "total_tokens"),
        error_kind=_optional_str(row, "error_kind"),
        error_message_user=_optional_str(row, "error_message_user"),
    )


def _count_stage_status(current: int, total: int, workflow_status: str) -> str:
    if workflow_status.upper() in {"FAILED"}:
        return "failed"
    if workflow_status.upper() == "PAUSED":
        return "paused"
    if total <= 0:
        return "pending"
    if current >= total:
        return "completed"
    if current > 0:
        return "running"
    return "pending"


def _stage_pending_or_running(workflow_status: str) -> str:
    if workflow_status.upper() == "PAUSED":
        return "paused"
    if workflow_status.upper() == "FAILED":
        return "failed"
    return "running" if workflow_status else "pending"


def _str(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be non-empty str")
    return value


def _optional_str(row: Mapping[str, object], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise TypeError(f"{key} must be str when set")
    return value


def _int(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if isinstance(value, bool):
        raise TypeError(f"{key} must be int")
    if isinstance(value, int):
        return value
    return 0


def _optional_int(row: Mapping[str, object], key: str) -> int | None:
    value = row.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{key} must be int when set")
    return value


def _optional_datetime(row: Mapping[str, object], key: str) -> datetime | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, datetime):
        raise TypeError(f"{key} must be datetime when set")
    return value


__all__ = [
    "WorkbenchWorkflowLiveStateDbPool",
    "WorkbenchWorkflowLiveStateNotFoundError",
    "WorkbenchWorkflowLiveStateQuery",
    "fetch_workbench_workflow_live_state",
]
