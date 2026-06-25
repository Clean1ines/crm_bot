from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime
from typing import Protocol
from uuid import uuid4

from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
)
from src.contexts.capacity_admission_queue.application.sync_capacity_admission_projection_lifecycle import (
    CAPACITY_ADMISSION_PROJECTED_LIFECYCLE_STATUSES,
    CapacityAdmissionProjectionLifecycleSyncResult,
    CapacityAdmissionProjectionLifecycleUpdate,
    CapacityAdmissionProjectionLifecycleSynchronizerPort,
)


class CapacityAdmissionProjectionLifecycleConnectionLike(Protocol):
    async def fetchrow(
        self, query: str, *args: object
    ) -> Mapping[str, object] | None: ...

    async def execute(self, query: str, *args: object) -> object: ...


class PostgresCapacityAdmissionProjectionLifecycleSynchronizer(
    CapacityAdmissionProjectionLifecycleSynchronizerPort,
):
    """Syncs Execution Runtime lifecycle status into admission projection.

    This adapter owns only Capacity Admission Queue projection and wakeup state.
    It does not mutate Execution Runtime work items, choose retry policy, reserve
    provider capacity, or encode Workbench semantics. Transaction ownership
    belongs to the composition boundary.
    """

    def __init__(
        self,
        connection: CapacityAdmissionProjectionLifecycleConnectionLike,
    ) -> None:
        self._connection = connection

    async def sync_projection_lifecycle(
        self,
        update: CapacityAdmissionProjectionLifecycleUpdate,
    ) -> CapacityAdmissionProjectionLifecycleSyncResult | None:
        row = await self._connection.fetchrow(
            """
            WITH selected AS (
                SELECT
                    work_item_id,
                    work_kind,
                    provider,
                    account_ref,
                    model_ref,
                    status AS previous_status
                FROM capacity_admission_work_items
                WHERE work_item_id = $1
                FOR UPDATE
            ),
            updated AS (
                UPDATE capacity_admission_work_items AS work_items
                SET
                    status = $2,
                    retry_plan = $3,
                    updated_at = $4,
                    model_ref = COALESCE($5, work_items.model_ref)
                FROM selected
                WHERE work_items.work_item_id = selected.work_item_id
                  AND (
                    work_items.status IS DISTINCT FROM $2
                    OR work_items.retry_plan IS DISTINCT FROM $3
                    OR (
                        $5::text IS NOT NULL
                        AND work_items.model_ref IS DISTINCT FROM $5
                    )
                  )
                RETURNING
                    work_items.work_item_id,
                    work_items.work_kind,
                    work_items.provider,
                    work_items.account_ref,
                    work_items.model_ref,
                    selected.previous_status,
                    work_items.status,
                    work_items.retry_plan
            )
            SELECT
                work_item_id,
                work_kind,
                provider,
                account_ref,
                model_ref,
                previous_status,
                status,
                retry_plan
            FROM updated
            """,
            update.work_item_id,
            update.status,
            update.retry_plan,
            update.changed_at,
            update.model_ref,
        )
        if row is None:
            return None

        lane_key = CapacityAdmissionLaneKey(
            work_kind=_required_str(row, "work_kind"),
            provider=_required_str(row, "provider"),
            account_ref=_optional_str(row, "account_ref"),
            model_ref=_required_str(row, "model_ref"),
        )
        event_type = _event_type_for_status(update.status)
        reason = _reason_for_status(update.status)
        event_id = uuid4()
        lane_id = _lane_id(lane_key)

        await self._mark_lane_dirty(
            lane_key=lane_key,
            lane_id=lane_id,
            reason=reason,
            occurred_at=update.changed_at,
        )
        await self._append_lane_event(
            lane_key=lane_key,
            lane_id=lane_id,
            event_id=event_id,
            event_type=event_type,
            work_item_id=update.work_item_id,
            reason=reason,
            payload={
                "work_item_id": update.work_item_id,
                "previous_status": _required_status(row, "previous_status"),
                "status": _required_status(row, "status"),
                "retry_plan": _optional_str(row, "retry_plan"),
                "model_ref": _required_str(row, "model_ref"),
            },
            occurred_at=update.changed_at,
        )

        return CapacityAdmissionProjectionLifecycleSyncResult(
            work_item_id=_required_str(row, "work_item_id"),
            lane_key=lane_key,
            previous_status=_required_status(row, "previous_status"),
            status=_required_status(row, "status"),
            retry_plan=_optional_str(row, "retry_plan"),
            event_type=event_type,
            reason=reason,
            event_id=event_id,
        )

    async def _mark_lane_dirty(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        lane_id: str,
        reason: str,
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
            lane_key.work_kind,
            lane_key.provider,
            lane_key.account_ref,
            lane_key.model_ref,
            reason,
            occurred_at,
            occurred_at,
        )

    async def _append_lane_event(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        lane_id: str,
        event_id: object,
        event_type: str,
        work_item_id: str,
        reason: str,
        payload: Mapping[str, object],
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
            str(event_id),
            lane_id,
            event_type,
            lane_key.work_kind,
            lane_key.provider,
            lane_key.account_ref,
            lane_key.model_ref,
            work_item_id,
            reason,
            _jsonb(payload),
            occurred_at,
        )


def _event_type_for_status(status: str) -> str:
    if status in {"ready", "retryable_failed"}:
        return "DueWorkQueueChanged"
    return "CapacityWindowChanged"


def _reason_for_status(status: str) -> str:
    if status == "retryable_failed":
        return "work_item_returned_retryable"
    if status == "ready":
        return "work_item_released_ready"
    if status == "split_superseded":
        return "leased_work_item_split_superseded"
    if status == "user_action_required":
        return "work_item_requires_user_action"
    return "attempt_finished_capacity_available"


def _lane_id(lane_key: CapacityAdmissionLaneKey) -> str:
    account_ref = lane_key.account_ref if lane_key.account_ref is not None else "-"
    return (
        f"{lane_key.work_kind}:{lane_key.provider}:{account_ref}:{lane_key.model_ref}"
    )


def _required_status(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if (
        isinstance(value, str)
        and value in CAPACITY_ADMISSION_PROJECTED_LIFECYCLE_STATUSES
    ):
        return value
    raise ValueError(f"{key} must be a known projection status")


def _required_str(row: Mapping[str, object], key: str) -> str:
    value = row.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a non-empty string")
    return value


def _optional_str(row: Mapping[str, object], key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be null or a non-empty string")
    return value


def _jsonb(value: Mapping[str, object]) -> str:
    return json.dumps(value, default=str, separators=(",", ":"), sort_keys=True)
