from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol
from uuid import uuid4

from src.contexts.capacity_admission_queue.application.admit_capacity_admission_work_item import (
    CapacityAdmissionProjectionLease,
    CapacityAdmissionProjectionLeaseResult,
)
from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
)


class CapacityAdmissionProjectionAdmitterConnectionLike(Protocol):
    async def fetchrow(
        self, query: str, *args: object
    ) -> Mapping[str, object] | None: ...

    async def execute(self, query: str, *args: object) -> object: ...


class PostgresCapacityAdmissionProjectionAdmitter:
    """Marks a selected capacity admission projection row as leased.

    This adapter owns only Capacity Admission Queue projection state. It does not
    mutate Execution Runtime work item lifecycle and does not create execution
    attempts or dispatches. Transaction ownership belongs to the composition
    boundary.
    """

    def __init__(
        self,
        connection: CapacityAdmissionProjectionAdmitterConnectionLike,
    ) -> None:
        self._connection = connection

    async def admit_projection_work_item(
        self,
        lease: CapacityAdmissionProjectionLease,
    ) -> CapacityAdmissionProjectionLeaseResult | None:
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
                  AND work_kind = $3
                  AND provider = $4
                  AND account_ref IS NOT DISTINCT FROM $5
                  AND model_ref = $6
                  AND status IN ('ready', 'retryable_failed')
                FOR UPDATE SKIP LOCKED
            ),
            updated AS (
                UPDATE capacity_admission_work_items AS work_items
                SET
                    status = 'leased',
                    updated_at = $2
                FROM selected
                WHERE work_items.work_item_id = selected.work_item_id
                RETURNING
                    work_items.work_item_id,
                    work_items.work_kind,
                    work_items.provider,
                    work_items.account_ref,
                    work_items.model_ref,
                    selected.previous_status,
                    work_items.status
            )
            SELECT
                work_item_id,
                work_kind,
                provider,
                account_ref,
                model_ref,
                previous_status,
                status
            FROM updated
            """,
            lease.work_item_id,
            lease.leased_at,
            lease.lane_key.work_kind,
            lease.lane_key.provider,
            lease.lane_key.account_ref,
            lease.lane_key.model_ref,
        )
        if row is None:
            return None

        previous_status = _required_previous_status(row)
        event_id = uuid4()

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
            ) VALUES (
                $1,
                $2,
                'CapacityWindowLeasedWorkItem',
                $3,
                $4,
                $5,
                $6,
                $7,
                $8,
                '{}'::jsonb,
                $9
            )
            """,
            event_id,
            _lane_id(lease.lane_key),
            lease.lane_key.work_kind,
            lease.lane_key.provider,
            lease.lane_key.account_ref,
            lease.lane_key.model_ref,
            lease.work_item_id,
            lease.lease_reason,
            lease.leased_at,
        )

        return CapacityAdmissionProjectionLeaseResult(
            work_item_id=_required_str(row, "work_item_id"),
            lane_key=CapacityAdmissionLaneKey(
                work_kind=_required_str(row, "work_kind"),
                provider=_required_str(row, "provider"),
                account_ref=_optional_str(row, "account_ref"),
                model_ref=_required_str(row, "model_ref"),
            ),
            previous_status=previous_status,
            status=_required_str(row, "status"),
            event_id=event_id,
        )


def _lane_id(lane_key: CapacityAdmissionLaneKey) -> str:
    account_ref = lane_key.account_ref if lane_key.account_ref is not None else "-"
    return (
        f"{lane_key.work_kind}:{lane_key.provider}:{account_ref}:{lane_key.model_ref}"
    )


def _required_previous_status(row: Mapping[str, object]) -> str:
    value = row.get("previous_status")
    if value in {"ready", "retryable_failed"}:
        return str(value)
    raise ValueError("previous_status must be ready or retryable_failed")


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
