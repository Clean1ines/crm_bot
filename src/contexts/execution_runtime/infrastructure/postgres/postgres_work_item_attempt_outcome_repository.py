from __future__ import annotations

import json
from collections.abc import Mapping
from datetime import datetime

import asyncpg

from src.contexts.execution_runtime.application.ports.work_item_attempt_outcome_repository_port import (
    RecordedWorkItemAttemptOutcome,
    WorkItemAttemptOutcomeRecord,
    WorkItemAttemptOutcomeRepositoryPort,
    WorkItemAttemptOutcomeStatus,
)
from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
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


class PostgresWorkItemAttemptOutcomeRepository(
    WorkItemAttemptOutcomeRepositoryPort,
):
    """Records execution attempt outcomes and applies generic work item transitions.

    Transaction ownership belongs to the composing application boundary.
    """

    def __init__(self, connection: asyncpg.Connection) -> None:
        self._connection = connection

    async def get_recorded_attempt_outcome(
        self,
        *,
        attempt_id: str,
    ) -> RecordedWorkItemAttemptOutcome | None:
        row = await self._connection.fetchrow(
            """
            SELECT
                w.work_item_id,
                w.work_kind,
                w.status,
                w.attempt_count,
                w.leased_by,
                w.lease_token,
                w.lease_expires_at,
                w.next_attempt_at,
                w.last_error_kind,
                a.attempt_id AS recorded_attempt_id,
                a.attempt_number AS recorded_attempt_number,
                a.finished_at AS recorded_finished_at,
                a.outcome_status AS recorded_outcome_status,
                a.error_kind AS recorded_error_kind,
                a.validation_metadata AS recorded_validation_metadata
            FROM execution_work_item_attempts a
            JOIN execution_work_items w
              ON w.work_item_id = a.work_item_id
            WHERE a.attempt_id = $1
              AND a.finished_at IS NOT NULL
              AND a.outcome_status IS NOT NULL
            """,
            attempt_id,
        )
        if row is None:
            return None

        finished_at = row["recorded_finished_at"]
        if not isinstance(finished_at, datetime):
            raise TypeError("recorded_finished_at must be datetime")

        attempt_number = row["recorded_attempt_number"]
        if not isinstance(attempt_number, int):
            raise TypeError("recorded_attempt_number must be int")

        next_attempt_at = row["next_attempt_at"]
        if next_attempt_at is not None and not isinstance(next_attempt_at, datetime):
            raise TypeError("next_attempt_at must be datetime or None")

        return RecordedWorkItemAttemptOutcome(
            attempt_id=str(row["recorded_attempt_id"]),
            work_item_id=str(row["work_item_id"]),
            attempt_number=attempt_number,
            finished_at=finished_at,
            outcome_status=WorkItemAttemptOutcomeStatus(
                str(row["recorded_outcome_status"]),
            ),
            error_kind=(
                str(row["recorded_error_kind"])
                if row["recorded_error_kind"] is not None
                else None
            ),
            next_attempt_at=next_attempt_at,
            validation_metadata=_validation_metadata_from_row(
                row["recorded_validation_metadata"],
            ),
            work_item=_hydrate_work_item(row),
        )

    async def record_attempt_outcome(
        self,
        record: WorkItemAttemptOutcomeRecord,
    ) -> WorkItem:
        row = await self._connection.fetchrow(
            """
            SELECT
                work_item_id,
                work_kind,
                status,
                attempt_count,
                leased_by,
                lease_token,
                lease_expires_at,
                next_attempt_at,
                last_error_kind
            FROM execution_work_items
            WHERE work_item_id = $1
            FOR UPDATE
            """,
            record.work_item_id,
        )
        if row is None:
            raise ValueError("work item does not exist")

        current = _hydrate_work_item(row)
        _validate_current_lease(current, record)

        transitioned = _transition_work_item(current, record)

        attempt_result = await self._connection.execute(
            """
            UPDATE execution_work_item_attempts
            SET
                finished_at = $2,
                outcome_status = $3,
                error_kind = $4,
                validation_metadata = $5::jsonb
            WHERE attempt_id = $1
              AND work_item_id = $6
              AND attempt_number = $7
            """,
            record.attempt_id,
            record.finished_at,
            record.outcome_status.value,
            record.error_kind,
            _jsonb_payload(record.validation_metadata),
            record.work_item_id,
            record.attempt_number,
        )
        _require_one_updated_row(
            attempt_result,
            message="attempt outcome update must affect exactly one row",
        )

        work_item_result = await self._connection.execute(
            """
            UPDATE execution_work_items
            SET
                status = $2,
                attempt_count = $3,
                leased_by = $4,
                lease_token = $5,
                lease_expires_at = $6,
                next_attempt_at = $7,
                last_error_kind = $8,
                updated_at = now()
            WHERE work_item_id = $1
            """,
            transitioned.work_item_id,
            transitioned.status.value,
            transitioned.attempt_count,
            _worker_ref_value(transitioned.leased_by),
            _lease_token_value(transitioned.lease_token),
            transitioned.lease_expires_at,
            _wait_until_value(transitioned.next_attempt_at),
            transitioned.last_error_kind,
        )
        _require_one_updated_row(
            work_item_result,
            message="work item outcome update must affect exactly one row",
        )

        return transitioned


def _jsonb_payload(payload: Mapping[str, object] | None) -> str | None:
    if payload is None:
        return None
    return json.dumps(dict(payload))


def _validation_metadata_from_row(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if isinstance(value, str):
        decoded = json.loads(value)
    elif isinstance(value, Mapping):
        decoded = dict(value)
    else:
        raise TypeError("validation_metadata must be json object or None")

    if not isinstance(decoded, dict):
        raise TypeError("validation_metadata must decode to object")

    result: dict[str, object] = {}
    for key, item in decoded.items():
        if not isinstance(key, str):
            raise TypeError("validation_metadata keys must be text")
        result[key] = item
    return result


def _validate_current_lease(
    current: WorkItem,
    record: WorkItemAttemptOutcomeRecord,
) -> None:
    if current.status is not WorkItemStatus.LEASED:
        raise ValueError("work item must be leased to record attempt outcome")
    if current.lease_token != record.lease_token:
        raise ValueError("lease_token does not match current work item lease")
    if current.attempt_count != record.attempt_number:
        raise ValueError(
            "attempt_number does not match current work item attempt_count"
        )


def _transition_work_item(
    current: WorkItem,
    record: WorkItemAttemptOutcomeRecord,
) -> WorkItem:
    if record.outcome_status is WorkItemAttemptOutcomeStatus.SUCCEEDED:
        return WorkItemStateMachine.complete_leased(current)

    if record.error_kind is None:
        raise ValueError("error_kind is required for failed/deferred outcomes")

    if record.outcome_status is WorkItemAttemptOutcomeStatus.RETRYABLE_FAILED:
        if record.next_attempt_at is None:
            raise ValueError("next_attempt_at is required for retryable failure")
        return WorkItemStateMachine.fail_leased_retryable(
            current,
            error_kind=record.error_kind,
            next_attempt_at=WaitUntil(record.next_attempt_at),
        )

    if record.outcome_status is WorkItemAttemptOutcomeStatus.TERMINAL_FAILED:
        return WorkItemStateMachine.fail_leased_terminal(
            current,
            error_kind=record.error_kind,
        )

    if record.outcome_status is WorkItemAttemptOutcomeStatus.DEFERRED:
        if record.next_attempt_at is None:
            raise ValueError("next_attempt_at is required for deferred outcome")
        return WorkItemStateMachine.defer_leased(
            current,
            wait_until=WaitUntil(record.next_attempt_at),
            error_kind=record.error_kind,
        )

    raise ValueError("unsupported attempt outcome status")


def _hydrate_work_item(row: asyncpg.Record) -> WorkItem:
    next_attempt_at = row["next_attempt_at"]
    return WorkItem(
        work_item_id=row["work_item_id"],
        work_kind=WorkKind(row["work_kind"]),
        status=WorkItemStatus(row["status"]),
        attempt_count=row["attempt_count"],
        leased_by=_worker_ref(row["leased_by"]),
        lease_token=_lease_token(row["lease_token"]),
        lease_expires_at=row["lease_expires_at"],
        next_attempt_at=WaitUntil(next_attempt_at)
        if next_attempt_at is not None
        else None,
        last_error_kind=row["last_error_kind"],
    )


def _worker_ref(value: str | None) -> WorkerRef | None:
    if value is None:
        return None
    return WorkerRef(value)


def _lease_token(value: str | None) -> LeaseToken | None:
    if value is None:
        return None
    return LeaseToken(value)


def _worker_ref_value(value: WorkerRef | None) -> str | None:
    if value is None:
        return None
    return value.value


def _lease_token_value(value: LeaseToken | None) -> str | None:
    if value is None:
        return None
    return value.value


def _wait_until_value(value: WaitUntil | None) -> datetime | None:
    if value is None:
        return None
    return value.value


def _require_one_updated_row(command_tag: str, *, message: str) -> None:
    if command_tag != "UPDATE 1":
        raise RuntimeError(message)
