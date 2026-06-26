from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
    CapacityAdmissionSelectableWorkItem,
)


class CapacityAdmissionWorkItemSelectorConnectionLike(Protocol):
    async def fetchrow(
        self, query: str, *args: object
    ) -> Mapping[str, object] | None: ...


class PostgresCapacityAdmissionWorkItemSelector:
    """Postgres selector for one capacity admission lane.

    Transaction ownership stays at the composition boundary. This adapter only
    selects the first fitting projection row and locks it for the surrounding
    transaction. It does not lease execution work, mutate projection status,
    reserve provider capacity, or dispatch work.
    """

    def __init__(
        self,
        connection: CapacityAdmissionWorkItemSelectorConnectionLike,
    ) -> None:
        self._connection = connection

    async def select_first_retryable_failed_fit(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        max_required_window_tokens: int,
    ) -> CapacityAdmissionSelectableWorkItem | None:
        return await self._select_first_fit(
            lane_key=lane_key,
            status="retryable_failed",
            max_required_window_tokens=max_required_window_tokens,
        )

    async def select_first_ready_fit(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        max_required_window_tokens: int,
    ) -> CapacityAdmissionSelectableWorkItem | None:
        return await self._select_first_fit(
            lane_key=lane_key,
            status="ready",
            max_required_window_tokens=max_required_window_tokens,
        )

    async def _select_first_fit(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        status: str,
        max_required_window_tokens: int,
    ) -> CapacityAdmissionSelectableWorkItem | None:
        if max_required_window_tokens <= 0:
            raise ValueError("max_required_window_tokens must be positive")

        row = await self._connection.fetchrow(
            """
            SELECT
                work_item_id,
                work_kind,
                provider,
                account_ref,
                model_ref,
                status,
                input_tokens,
                artifact_tokens,
                required_window_tokens
            FROM capacity_admission_work_items
            WHERE work_kind = $1
              AND provider = $2
              AND account_ref IS NOT DISTINCT FROM $3
              AND model_ref = $4
              AND status = $5
              AND required_window_tokens <= $6
            ORDER BY updated_at ASC, work_item_id ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
            """,
            lane_key.work_kind,
            lane_key.provider,
            lane_key.account_ref,
            lane_key.model_ref,
            status,
            max_required_window_tokens,
        )
        if row is None:
            return None

        return _row_to_selectable_work_item(row)


def _row_to_selectable_work_item(
    row: Mapping[str, object],
) -> CapacityAdmissionSelectableWorkItem:
    row_status = _required_str(row, "status")
    if row_status not in {"retryable_failed", "ready"}:
        raise ValueError(f"unsupported capacity admission status: {row_status}")

    lane_key = CapacityAdmissionLaneKey(
        work_kind=_required_str(row, "work_kind"),
        provider=_required_str(row, "provider"),
        account_ref=_optional_str(row, "account_ref"),
        model_ref=_required_str(row, "model_ref"),
    )

    if row_status == "retryable_failed":
        return CapacityAdmissionSelectableWorkItem(
            work_item_id=_required_str(row, "work_item_id"),
            lane_key=lane_key,
            status="retryable_failed",
            required_window_tokens=_required_positive_int(
                row,
                "required_window_tokens",
            ),
            input_tokens=_optional_positive_int(
                row,
                "input_tokens",
            ),
            artifact_tokens=_optional_non_negative_int(
                row,
                "artifact_tokens",
            ),
        )

    return CapacityAdmissionSelectableWorkItem(
        work_item_id=_required_str(row, "work_item_id"),
        lane_key=lane_key,
        status="ready",
        required_window_tokens=_required_positive_int(
            row,
            "required_window_tokens",
        ),
        input_tokens=_optional_positive_int(
            row,
            "input_tokens",
        ),
        artifact_tokens=_optional_non_negative_int(
            row,
            "artifact_tokens",
        ),
    )


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


def _required_positive_int(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{key} must be a positive integer")
    return value


def _optional_positive_int(row: Mapping[str, object], key: str) -> int | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{key} must be null or a positive integer")
    return value


def _optional_non_negative_int(row: Mapping[str, object], key: str) -> int | None:
    value = row.get(key)
    if value is None:
        return None
    if not isinstance(value, int) or value < 0:
        raise ValueError(f"{key} must be null or a non-negative integer")
    return value
