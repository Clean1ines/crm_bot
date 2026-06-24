from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from src.contexts.capacity_admission_queue.application.build_capacity_admission_projection_candidates import (
    CapacityAdmissionWorkItemProjectionCandidate,
)
from src.contexts.capacity_admission_queue.application.ports.capacity_admission_projection_writer_port import (
    CapacityAdmissionProjectionWriterPort,
    PersistCapacityAdmissionProjectionResult,
)


class CapacityAdmissionProjectionWriterConnectionLike(Protocol):
    async def execute(self, query: str, *args: object) -> object: ...


class PostgresCapacityAdmissionProjectionWriter(CapacityAdmissionProjectionWriterPort):
    """Postgres adapter for Capacity Admission Queue projection writes.

    Transaction ownership stays at the composition boundary. This adapter upserts
    admission projection rows and records lane wakeups on the provided connection.
    It does not lease work, reserve provider capacity, or dispatch admission passes.
    """

    def __init__(
        self,
        connection: CapacityAdmissionProjectionWriterConnectionLike,
    ) -> None:
        self._connection = connection

    async def persist_projection_candidates(
        self,
        candidates: tuple[CapacityAdmissionWorkItemProjectionCandidate, ...],
    ) -> PersistCapacityAdmissionProjectionResult:
        if not isinstance(candidates, tuple):
            raise TypeError("candidates must be tuple")
        if not candidates:
            return PersistCapacityAdmissionProjectionResult(persisted_count=0)

        occurred_at = _utc_now()
        dirty_lanes: set[str] = set()

        for candidate in candidates:
            if not isinstance(candidate, CapacityAdmissionWorkItemProjectionCandidate):
                raise TypeError(
                    "candidates must contain CapacityAdmissionWorkItemProjectionCandidate"
                )
            await self._persist_candidate(candidate, occurred_at=occurred_at)
            lane_id = _lane_id(candidate)
            if lane_id not in dirty_lanes:
                await self._mark_lane_dirty(
                    candidate, lane_id=lane_id, occurred_at=occurred_at
                )
                await self._append_due_work_queue_changed_event(
                    candidate,
                    lane_id=lane_id,
                    occurred_at=occurred_at,
                )
                dirty_lanes.add(lane_id)

        return PersistCapacityAdmissionProjectionResult(
            persisted_count=len(candidates),
        )

    async def _persist_candidate(
        self,
        candidate: CapacityAdmissionWorkItemProjectionCandidate,
        *,
        occurred_at: datetime,
    ) -> None:
        await self._connection.execute(
            """
            INSERT INTO capacity_admission_work_items (
                work_item_id,
                work_kind,
                workflow_run_id,
                project_id,
                provider,
                account_ref,
                model_ref,
                status,
                retry_plan,
                estimated_input_tokens,
                estimated_output_tokens,
                effective_output_cap_tokens,
                reserved_total_tokens,
                source_ref,
                created_at,
                updated_at
            )
            VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9,
                $10, $11, $12, $13, $14::jsonb, $15, $16
            )
            ON CONFLICT (work_item_id) DO UPDATE SET
                work_kind = EXCLUDED.work_kind,
                workflow_run_id = EXCLUDED.workflow_run_id,
                project_id = EXCLUDED.project_id,
                provider = EXCLUDED.provider,
                account_ref = EXCLUDED.account_ref,
                model_ref = EXCLUDED.model_ref,
                status = EXCLUDED.status,
                retry_plan = EXCLUDED.retry_plan,
                estimated_input_tokens = EXCLUDED.estimated_input_tokens,
                estimated_output_tokens = EXCLUDED.estimated_output_tokens,
                effective_output_cap_tokens = EXCLUDED.effective_output_cap_tokens,
                reserved_total_tokens = EXCLUDED.reserved_total_tokens,
                source_ref = EXCLUDED.source_ref,
                updated_at = EXCLUDED.updated_at
            """,
            candidate.work_item_id,
            candidate.work_kind,
            candidate.workflow_run_id,
            candidate.project_id,
            candidate.provider,
            candidate.account_ref,
            candidate.model_ref,
            candidate.status.value,
            candidate.retry_plan,
            candidate.estimated_input_tokens,
            candidate.estimated_output_tokens,
            candidate.effective_output_cap_tokens,
            candidate.reserved_total_tokens,
            _jsonb(candidate.source_ref),
            occurred_at,
            occurred_at,
        )

    async def _mark_lane_dirty(
        self,
        candidate: CapacityAdmissionWorkItemProjectionCandidate,
        *,
        lane_id: str,
        occurred_at: datetime,
    ) -> None:
        await self._connection.execute(
            """
            INSERT INTO capacity_admission_lane_dirty_flags (
                lane_id,
                work_kind,
                provider,
                account_ref,
                model_ref,
                dirty_reason,
                dirty_count,
                first_marked_at,
                last_marked_at,
                claimed_by,
                claimed_until
            )
            VALUES ($1, $2, $3, $4, $5, $6, 1, $7, $8, NULL, NULL)
            ON CONFLICT (lane_id) DO UPDATE SET
                dirty_reason = EXCLUDED.dirty_reason,
                dirty_count = capacity_admission_lane_dirty_flags.dirty_count + 1,
                last_marked_at = EXCLUDED.last_marked_at,
                claimed_by = NULL,
                claimed_until = NULL
            """,
            lane_id,
            candidate.work_kind,
            candidate.provider,
            candidate.account_ref,
            candidate.model_ref,
            "scheduled_projection_upserted",
            occurred_at,
            occurred_at,
        )

    async def _append_due_work_queue_changed_event(
        self,
        candidate: CapacityAdmissionWorkItemProjectionCandidate,
        *,
        lane_id: str,
        occurred_at: datetime,
    ) -> None:
        await self._connection.execute(
            """
            INSERT INTO capacity_admission_lane_events (
                event_id,
                lane_id,
                event_type,
                work_kind,
                provider,
                account_ref,
                model_ref,
                work_item_id,
                reason,
                payload,
                occurred_at
            )
            VALUES ($1::uuid, $2, $3, $4, $5, $6, $7, $8, $9, $10::jsonb, $11)
            """,
            str(uuid4()),
            lane_id,
            "DueWorkQueueChanged",
            candidate.work_kind,
            candidate.provider,
            candidate.account_ref,
            candidate.model_ref,
            candidate.work_item_id,
            "scheduled_projection_upserted",
            _jsonb(
                {
                    "work_item_id": candidate.work_item_id,
                    "status": candidate.status.value,
                    "reserved_total_tokens": candidate.reserved_total_tokens,
                }
            ),
            occurred_at,
        )


def _lane_id(candidate: CapacityAdmissionWorkItemProjectionCandidate) -> str:
    account_ref = candidate.account_ref if candidate.account_ref is not None else "-"
    return (
        f"{candidate.work_kind}:"
        f"{candidate.provider}:"
        f"{account_ref}:"
        f"{candidate.model_ref}"
    )


def _jsonb(value: Mapping[str, object]) -> str:
    return json.dumps(value, default=str, separators=(",", ":"), sort_keys=True)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)
