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
    WorkbenchWorkflowTimelineEntryLiveView,
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
            document_id=document_id,
            workflow_run_id=workflow_run_id,
        )
        attempts = await self._llm_attempts(
            document_id=document_id,
            workflow_run_id=workflow_run_id,
        )
        model_summaries = await self._model_summaries(
            workflow_run_id=workflow_run_id,
        )
        counts = await self._counts(
            document_id=document_id,
            workflow_run_id=workflow_run_id,
        )
        timeline = await self._timeline(workflow_run_id=workflow_run_id)
        timer_events = await self._timer_events(workflow_run_id=workflow_run_id)
        curation = await self._curation(
            workflow_run_id=workflow_run_id,
            preview_ready=_int(counts, "preview_count") > 0,
            compacted_done=_int(counts, "active_compacted_nodes") > 0,
        )
        degraded_fallback_confirmation_pending = (
            await self._degraded_fallback_confirmation_pending(
                workflow_run_id=workflow_run_id
            )
        )

        timer = _timer(document_row, timer_events=timer_events)
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
            timeline=timeline,
            curation=curation,
            actions=_actions(
                workflow_status=workflow_status,
                curation=curation,
                degraded_fallback_confirmation_pending=(
                    degraded_fallback_confirmation_pending
                ),
            ),
        )
        return WorkbenchDocumentWorkflowLiveState(
            document_id=_str(document_row, "document_id"),
            project_id=_str(document_row, "project_id"),
            file_name=_str(document_row, "file_name"),
            document_status=_str(document_row, "document_status"),
            current_processing_run_id=processing_run_id,
            workflow=workflow,
        )

    async def _degraded_fallback_confirmation_pending(
        self,
        *,
        workflow_run_id: str | None,
    ) -> bool:
        if workflow_run_id is None:
            return False
        value = await self._connection.fetchval(
            """
            SELECT EXISTS (
                SELECT 1
                FROM workflow_runtime_outbox_events AS waiting
                WHERE waiting.workflow_run_id = $1
                  AND waiting.event_type =
                      'DraftClaimCompactionWaitingUserModelChoice'
                  AND waiting.payload->>'reason' =
                      'primary_model_daily_capacity_exhausted'
                  AND NOT EXISTS (
                      SELECT 1
                      FROM workflow_runtime_outbox_events AS resolved
                      WHERE resolved.workflow_run_id = waiting.workflow_run_id
                        AND resolved.event_type =
                            'DraftClaimCompactionUserModelChoiceResolved'
                        AND resolved.causation_command_id =
                            waiting.causation_command_id
                  )
            )
            """,
            workflow_run_id,
        )
        return value is True

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
                wf.workflow_run_id,
                wf.source_document_ref,
                wf.status AS workflow_status,
                COALESCE(ps.current_phase, wf.current_phase) AS current_phase,
                wf.completed_at AS workflow_completed_at,
                wf.cancelled_at AS workflow_cancelled_at,
                ps.started_at AS started_at,
                ps.completed_at AS completed_at,
                CASE
                  WHEN wf.status IN ('RUNNING', 'ACTIVE', 'PROCESSING')
                    AND ps.started_at IS NOT NULL
                  THEN ps.started_at
                  ELSE NULL
                END AS current_active_started_at,
                CASE
                  WHEN ps.started_at IS NULL THEN 0
                  WHEN wf.status IN ('RUNNING', 'ACTIVE', 'PROCESSING')
                  THEN GREATEST(0, EXTRACT(EPOCH FROM (NOW() - ps.started_at))::int)
                  WHEN ps.completed_at IS NOT NULL
                  THEN GREATEST(0, EXTRACT(EPOCH FROM (ps.completed_at - ps.started_at))::int)
                  ELSE GREATEST(0, EXTRACT(EPOCH FROM (NOW() - ps.started_at))::int)
                END AS active_elapsed_seconds,
                CASE
                  WHEN ps.started_at IS NULL THEN 0
                  WHEN ps.completed_at IS NOT NULL
                  THEN GREATEST(0, EXTRACT(EPOCH FROM (ps.completed_at - ps.started_at))::int)
                  ELSE GREATEST(0, EXTRACT(EPOCH FROM (NOW() - ps.started_at))::int)
                END AS wall_elapsed_seconds,
                COALESCE(ru.input_tokens, 0)::int AS total_prompt_tokens,
                COALESCE(ru.output_tokens, 0)::int AS total_completion_tokens,
                COALESCE(ru.total_tokens, 0)::int AS total_tokens,
                COALESCE(ru.request_count, 0)::int AS total_llm_calls
            FROM knowledge_workbench_documents AS d
            LEFT JOIN LATERAL (
                SELECT w.*
                FROM knowledge_extraction_workflow_runs AS w
                WHERE w.project_id = d.project_id::text
                  AND w.source_document_ref = d.document_id
                ORDER BY w.updated_at DESC, w.created_at DESC
                LIMIT 1
            ) AS wf ON TRUE
            LEFT JOIN workflow_runtime_progress_snapshots AS ps
              ON ps.workflow_run_id = wf.workflow_run_id
            LEFT JOIN workflow_runtime_resource_usage_snapshots AS ru
              ON ru.workflow_run_id = wf.workflow_run_id
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
        document_id: str,
        workflow_run_id: str | None,
    ) -> tuple[WorkbenchSectionLaneLiveView, ...]:
        if workflow_run_id is None:
            return ()

        rows = await self._connection.fetch(
            """
            SELECT
                wi.work_item_id AS queue_item_id,
                COALESCE(s.payload->>'source_unit_ref', wi.work_item_id) AS section_id,
                COALESCE((s.payload->>'source_unit_ordinal')::int, 0) AS section_index,
                COALESCE(s.payload->>'source_unit_ref', wi.work_item_id) AS section_key,
                'execution-runtime' AS lane_id,
                0 AS lane_index,
                wi.status,
                wi.leased_by AS claimed_by_worker_id,
                wi.lease_expires_at,
                wi.next_attempt_at,
                wi.last_error_kind AS error_kind,
                wi.retry_plan,
                COALESCE(wi.attempt_count, 0) AS attempt_count
            FROM execution_work_items AS wi
            JOIN execution_work_item_schedules AS s
              ON s.work_item_id = wi.work_item_id
            WHERE s.payload->>'source_document_ref' = $1
              AND s.payload->>'workflow_run_id' = $2
              AND s.payload->>'phase' = 'claim_builder_section_extraction'
            ORDER BY
                COALESCE((s.payload->>'source_unit_ordinal')::int, 0) ASC,
                wi.work_item_id ASC
            LIMIT 500
            """,
            document_id,
            workflow_run_id,
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
        document_id: str,
        workflow_run_id: str | None,
    ) -> tuple[WorkbenchLlmAttemptLiveView, ...]:
        if workflow_run_id is None:
            return ()

        rows = await self._connection.fetch(
            """
            SELECT
                a.attempt_id AS node_run_id,
                s.payload->>'source_unit_ref' AS section_id,
                wi.work_kind AS node_name,
                'execution_work_item' AS node_kind,
                COALESCE(a.outcome_status, wi.status) AS status,
                a.started_at,
                a.finished_at AS completed_at,
                CASE
                  WHEN a.finished_at IS NULL THEN NULL
                  ELSE GREATEST(0, EXTRACT(EPOCH FROM (a.finished_at - a.started_at))::int * 1000)
                END AS duration_ms,
                COALESCE(
                    d.llm_allocation_payload->>'provider',
                    d.dispatch_payload #>> '{llm_allocation,provider}'
                ) AS model_provider,
                COALESCE(
                    d.llm_allocation_payload->>'account_ref',
                    d.dispatch_payload #>> '{llm_allocation,account_ref}'
                ) AS account_ref,
                COALESCE(
                    d.llm_allocation_payload->>'model_ref',
                    d.llm_allocation_payload->>'model',
                    d.dispatch_payload #>> '{llm_allocation,model_ref}',
                    d.dispatch_payload #>> '{llm_allocation,model}'
                ) AS model_name,
                COALESCE(obs.actual_prompt_tokens, 0)::int AS prompt_tokens,
                COALESCE(obs.actual_completion_tokens, 0)::int AS completion_tokens,
                COALESCE(
                    obs.actual_total_tokens,
                    COALESCE(obs.actual_prompt_tokens, 0)
                    + COALESCE(obs.actual_completion_tokens, 0),
                    0
                )::int AS total_tokens,
                a.error_kind,
                wi.last_error_kind AS error_message_user,
                wi.next_attempt_at,
                wi.retry_plan,
                wi.status AS work_item_status,
                obs.remaining_minute_requests,
                obs.remaining_minute_tokens,
                obs.minute_reset_at,
                obs.remaining_daily_requests,
                obs.remaining_daily_tokens,
                obs.daily_reset_at
            FROM execution_work_item_attempts AS a
            JOIN execution_work_items AS wi
              ON wi.work_item_id = a.work_item_id
            JOIN execution_work_item_schedules AS s
              ON s.work_item_id = wi.work_item_id
            LEFT JOIN execution_work_item_attempt_dispatches AS d
              ON d.attempt_id = a.attempt_id
            LEFT JOIN LATERAL (
                SELECT
                    capacity_obs.actual_prompt_tokens,
                    capacity_obs.actual_completion_tokens,
                    capacity_obs.actual_total_tokens,
                    capacity_obs.remaining_minute_requests,
                    capacity_obs.remaining_minute_tokens,
                    capacity_obs.minute_reset_at,
                    capacity_obs.remaining_daily_requests,
                    capacity_obs.remaining_daily_tokens,
                    capacity_obs.daily_reset_at
                FROM llm_attempt_capacity_observations AS capacity_obs
                WHERE capacity_obs.provider = COALESCE(
                    d.llm_allocation_payload->>'provider',
                    d.dispatch_payload #>> '{llm_allocation,provider}'
                )
                  AND capacity_obs.account_ref = COALESCE(
                    d.llm_allocation_payload->>'account_ref',
                    d.dispatch_payload #>> '{llm_allocation,account_ref}'
                  )
                  AND capacity_obs.model_ref = COALESCE(
                    d.llm_allocation_payload->>'model_ref',
                    d.llm_allocation_payload->>'model',
                    d.dispatch_payload #>> '{llm_allocation,model_ref}',
                    d.dispatch_payload #>> '{llm_allocation,model}'
                  )
                  AND a.finished_at IS NOT NULL
                  AND capacity_obs.observed_at BETWEEN
                    a.finished_at - INTERVAL '30 seconds'
                    AND a.finished_at + INTERVAL '30 seconds'
                ORDER BY ABS(EXTRACT(EPOCH FROM (capacity_obs.observed_at - a.finished_at))) ASC
                LIMIT 1
            ) AS obs ON TRUE
            WHERE s.payload->>'source_document_ref' = $1
              AND s.payload->>'workflow_run_id' = $2
            ORDER BY a.started_at DESC, a.created_at DESC
            LIMIT 100
            """,
            document_id,
            workflow_run_id,
        )
        return tuple(_attempt(dict(row)) for row in rows)

    async def _model_summaries(
        self,
        *,
        workflow_run_id: str | None,
    ) -> tuple[WorkbenchWorkflowModelUsageLiveView, ...]:
        if workflow_run_id is None:
            return ()

        rows = await self._connection.fetch(
            """
            SELECT
                provider.key AS model_provider,
                NULL::text AS model_name,
                0::int AS call_count,
                0::int AS prompt_tokens,
                0::int AS completion_tokens,
                0::int AS total_tokens,
                0::int AS duration_ms_total
            FROM workflow_runtime_resource_usage_snapshots AS ru
            CROSS JOIN LATERAL jsonb_each(ru.provider_breakdown) AS provider(key, value)
            WHERE ru.workflow_run_id = $1
            ORDER BY provider.key ASC
            """,
            workflow_run_id,
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
        document_id: str,
        workflow_run_id: str | None,
    ) -> Mapping[str, object]:
        row = await self._connection.fetchrow(
            """
            SELECT
                (
                    SELECT COUNT(*)::int
                    FROM source_units AS u
                    WHERE u.document_ref = $1
                ) AS source_section_count,
                (
                    SELECT COUNT(*)::int
                    FROM draft_claim_observations AS o
                    JOIN source_units AS u
                      ON u.unit_ref = o.source_unit_ref
                    WHERE u.document_ref = $1
                ) AS draft_claim_count,
                (
                    SELECT COUNT(*)::int
                    FROM draft_claim_embeddings AS e
                    WHERE e.workflow_run_id = $2
                ) AS draft_claim_embedding_count,
                (
                    SELECT COUNT(*)::int
                    FROM draft_claim_compaction_nodes AS n
                    WHERE n.workflow_run_id = $2
                      AND n.node_kind = 'compacted'
                      AND n.active IS TRUE
                ) AS active_compacted_nodes,
                (
                    SELECT COUNT(*)::int
                    FROM draft_claim_compaction_comparisons AS c
                    WHERE c.workflow_run_id = $2
                      AND c.status IN ('pending', 'waiting_user_model_choice')
                ) AS pending_compaction_comparisons,
                (
                    SELECT COUNT(*)::int
                    FROM draft_claim_cluster_previews AS p
                    WHERE p.workflow_run_id = $2
                ) AS preview_count
            """,
            document_id,
            workflow_run_id,
        )
        return dict(row) if row is not None else {}

    async def _timeline(
        self,
        *,
        workflow_run_id: str | None,
    ) -> tuple[WorkbenchWorkflowTimelineEntryLiveView, ...]:
        if workflow_run_id is None:
            return ()

        rows = await self._connection.fetch(
            """
            SELECT
                timeline_entry_id,
                event_type,
                phase,
                severity,
                message,
                occurred_at,
                source_ref,
                work_item_id,
                attempt_id
            FROM workflow_runtime_timeline_entries
            WHERE workflow_run_id = $1
            ORDER BY occurred_at DESC
            LIMIT 20
            """,
            workflow_run_id,
        )
        return tuple(_timeline_entry(dict(row)) for row in rows)

    async def _timer_events(
        self,
        *,
        workflow_run_id: str | None,
    ) -> tuple[Mapping[str, object], ...]:
        if workflow_run_id is None:
            return ()

        rows = await self._connection.fetch(
            """
            SELECT
                event_type,
                occurred_at
            FROM workflow_runtime_timeline_entries
            WHERE workflow_run_id = $1
              AND event_type IN ('WorkflowManuallyPaused', 'WorkflowManuallyResumed')
            ORDER BY occurred_at ASC
            """,
            workflow_run_id,
        )
        return tuple(dict(row) for row in rows)

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


def _timer(
    row: Mapping[str, object],
    *,
    timer_events: tuple[Mapping[str, object], ...],
) -> WorkbenchWorkflowTimerLiveView:
    workflow_status = (_optional_str(row, "workflow_status") or "").upper()
    started_at = _optional_datetime(row, "started_at")
    completed_at = _optional_datetime(
        row, "workflow_completed_at"
    ) or _optional_datetime(row, "completed_at")
    now = datetime.now(timezone.utc)

    if workflow_status in {"RUNNING", "ACTIVE", "PROCESSING"}:
        mode = "running"
    elif workflow_status == "PAUSED":
        mode = "paused"
    elif workflow_status in {"COMPLETED", "DONE"}:
        mode = "completed"
    else:
        mode = "stopped"

    timer_end = completed_at if completed_at is not None else now
    active_elapsed_seconds, current_active_started_at = _active_timer_state(
        started_at=started_at,
        timer_end=timer_end,
        workflow_status=workflow_status,
        timer_events=timer_events,
    )

    wall_elapsed_seconds = 0
    if started_at is not None:
        wall_elapsed_seconds = max(0, int((timer_end - started_at).total_seconds()))

    return WorkbenchWorkflowTimerLiveView(
        mode=mode,
        active_elapsed_seconds=active_elapsed_seconds,
        wall_elapsed_seconds=wall_elapsed_seconds,
        current_active_started_at=current_active_started_at,
        started_at=started_at,
        completed_at=completed_at,
        is_live=mode == "running" and current_active_started_at is not None,
    )


def _active_timer_state(
    *,
    started_at: datetime | None,
    timer_end: datetime,
    workflow_status: str,
    timer_events: tuple[Mapping[str, object], ...],
) -> tuple[int, datetime | None]:
    if started_at is None:
        return 0, None

    active_seconds = 0
    active_segment_started_at: datetime | None = started_at
    paused = False

    for event in timer_events:
        event_type = _optional_str(event, "event_type")
        occurred_at = _optional_datetime(event, "occurred_at")
        if occurred_at is None or occurred_at < started_at or occurred_at > timer_end:
            continue

        if event_type == "WorkflowManuallyPaused" and not paused:
            if active_segment_started_at is not None:
                active_seconds += max(
                    0,
                    int((occurred_at - active_segment_started_at).total_seconds()),
                )
            active_segment_started_at = None
            paused = True
            continue

        if event_type == "WorkflowManuallyResumed" and paused:
            active_segment_started_at = occurred_at
            paused = False

    if workflow_status in {"RUNNING", "ACTIVE", "PROCESSING"} and not paused:
        return active_seconds, active_segment_started_at

    if active_segment_started_at is not None and not paused:
        active_seconds += max(
            0,
            int((timer_end - active_segment_started_at).total_seconds()),
        )

    return active_seconds, None


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
    degraded_fallback_confirmation_pending: bool,
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
        WorkbenchWorkflowActionView(
            action_id="confirm_degraded_fallback",
            visible=degraded_fallback_confirmation_pending,
            enabled=degraded_fallback_confirmation_pending and not terminal,
            reason_code=None
            if degraded_fallback_confirmation_pending and not terminal
            else "fallback_confirmation_not_pending",
        ),
    )


def _queue_item(row: Mapping[str, object]) -> WorkbenchSectionQueueItemLiveView:
    lease_expires_at = _optional_datetime(row, "lease_expires_at")
    next_attempt_at = _optional_datetime(row, "next_attempt_at")
    retry_available_at = next_attempt_at or lease_expires_at
    retry_seconds = None
    if retry_available_at is not None:
        retry_seconds = max(
            0, int((retry_available_at - datetime.now(timezone.utc)).total_seconds())
        )
    status = _str(row, "status")
    error_kind = _optional_str(row, "error_kind")
    return WorkbenchSectionQueueItemLiveView(
        queue_item_id=_str(row, "queue_item_id"),
        section_id=_str(row, "section_id"),
        section_index=_int(row, "section_index"),
        section_key=_str(row, "section_key"),
        status=status,
        attempt_count=_int(row, "attempt_count"),
        lease_expires_at=lease_expires_at,
        next_attempt_at=next_attempt_at,
        claimed_by_worker_id=_optional_str(row, "claimed_by_worker_id"),
        error_kind=error_kind,
        retry_plan=_optional_str(row, "retry_plan"),
        user_action_required=status == "user_action_required",
        blocked_reason=error_kind if status == "user_action_required" else None,
        retry_timer=WorkbenchRetryTimerLiveView(
            retry_available_at=retry_available_at,
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
        failed_count=sum(1 for item in items if item.status in _FAILED_QUEUE_STATUSES),
        waiting_count=sum(
            1
            for item in items
            if item.status.startswith("waiting")
            or item.status in _WAITING_QUEUE_STATUSES
        ),
        total_attempt_count=sum(item.attempt_count for item in items),
        max_attempt_count=max((item.attempt_count for item in items), default=0),
        items=items,
    )


_DONE_QUEUE_STATUSES = frozenset(
    {
        "completed",
        "claim_observations_persisted",
        "registry_application_queued",
        "registry_application_applied",
        "waiting_for_fresh_registry",
    }
)

_FAILED_QUEUE_STATUSES = frozenset(
    {
        "failed",
        "retryable_failed",
        "terminal_failed",
    }
)

_WAITING_QUEUE_STATUSES = frozenset(
    {
        "deferred",
        "user_action_required",
    }
)


def _timeline_entry(
    row: Mapping[str, object],
) -> WorkbenchWorkflowTimelineEntryLiveView:
    return WorkbenchWorkflowTimelineEntryLiveView(
        timeline_entry_id=_str(row, "timeline_entry_id"),
        event_type=_str(row, "event_type"),
        phase=_str(row, "phase"),
        severity=_str(row, "severity"),
        message=_str(row, "message"),
        occurred_at=_optional_datetime(row, "occurred_at")
        or datetime.now(timezone.utc),
        source_ref=_optional_str(row, "source_ref"),
        work_item_id=_optional_str(row, "work_item_id"),
        attempt_id=_optional_str(row, "attempt_id"),
    )


def _attempt(row: Mapping[str, object]) -> WorkbenchLlmAttemptLiveView:
    work_item_status = _optional_str(row, "work_item_status")
    last_error_kind = _optional_str(row, "error_message_user")
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
        account_ref=_optional_str(row, "account_ref"),
        prompt_tokens=_int(row, "prompt_tokens"),
        completion_tokens=_int(row, "completion_tokens"),
        total_tokens=_int(row, "total_tokens"),
        remaining_minute_requests=_optional_int(row, "remaining_minute_requests"),
        remaining_minute_tokens=_optional_int(row, "remaining_minute_tokens"),
        minute_reset_at=_optional_datetime(row, "minute_reset_at"),
        remaining_daily_requests=_optional_int(row, "remaining_daily_requests"),
        remaining_daily_tokens=_optional_int(row, "remaining_daily_tokens"),
        daily_reset_at=_optional_datetime(row, "daily_reset_at"),
        error_kind=_optional_str(row, "error_kind"),
        error_message_user=last_error_kind,
        next_attempt_at=_optional_datetime(row, "next_attempt_at"),
        retry_plan=_optional_str(row, "retry_plan"),
        user_action_required=work_item_status == "user_action_required",
        blocked_reason=last_error_kind
        if work_item_status == "user_action_required"
        else None,
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
