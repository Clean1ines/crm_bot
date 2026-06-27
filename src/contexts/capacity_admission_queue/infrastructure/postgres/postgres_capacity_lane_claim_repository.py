from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from src.contexts.capacity_admission_queue.application.ports.capacity_lane_claim_repository_port import (
    CapacityLaneClaim,
    CapacityLaneClaimRepositoryPort,
)
from src.contexts.capacity_admission_queue.application.select_capacity_admission_work_item import (
    CapacityAdmissionLaneKey,
)


class CapacityLaneClaimConnectionLike(Protocol):
    async def fetchrow(
        self, query: str, *args: object
    ) -> Mapping[str, object] | None: ...

    async def execute(self, query: str, *args: object) -> object: ...


class PostgresCapacityLaneClaimRepository(CapacityLaneClaimRepositoryPort):
    def __init__(self, connection: CapacityLaneClaimConnectionLike) -> None:
        self._connection = connection

    async def claim_dirty_lane(
        self,
        *,
        lane_key: CapacityAdmissionLaneKey,
        worker_ref: str,
        now: datetime,
        claim_ttl_seconds: int,
    ) -> CapacityLaneClaim | None:
        if claim_ttl_seconds <= 0:
            raise ValueError("claim_ttl_seconds must be positive")
        lane_id = _lane_id(lane_key)
        row = await self._connection.fetchrow(
            """
            WITH claimable AS (
                SELECT lane_id, work_kind, provider, account_ref, model_ref
                FROM capacity_admission_lane_dirty_flags
                WHERE lane_id = $1
                  AND work_kind = $2
                  AND provider = $3
                  AND account_ref IS NOT DISTINCT FROM $4
                  AND model_ref = $5
                  AND (claimed_by IS NULL OR claimed_until <= $6)
                FOR UPDATE SKIP LOCKED
            ),
            upsert_claim AS (
                INSERT INTO capacity_admission_lane_claims (
                    lane_id,
                    work_kind,
                    provider,
                    account_ref,
                    model_ref,
                    claimed_by,
                    claimed_until,
                    claimed_at,
                    claim_version
                )
                SELECT
                    lane_id,
                    work_kind,
                    provider,
                    account_ref,
                    model_ref,
                    $7,
                    $6 + make_interval(secs => $8),
                    $6,
                    1
                FROM claimable
                ON CONFLICT (lane_id) DO UPDATE SET
                    claimed_by = EXCLUDED.claimed_by,
                    claimed_until = EXCLUDED.claimed_until,
                    claimed_at = EXCLUDED.claimed_at,
                    claim_version = capacity_admission_lane_claims.claim_version + 1
                RETURNING
                    lane_id,
                    work_kind,
                    provider,
                    account_ref,
                    model_ref,
                    claimed_by,
                    claimed_until,
                    claim_version
            ),
            update_dirty AS (
                UPDATE capacity_admission_lane_dirty_flags AS dirty
                SET
                    claimed_by = upsert_claim.claimed_by,
                    claimed_until = upsert_claim.claimed_until
                FROM upsert_claim
                WHERE dirty.lane_id = upsert_claim.lane_id
                RETURNING upsert_claim.*
            )
            SELECT *
            FROM update_dirty
            """,
            lane_id,
            lane_key.work_kind,
            lane_key.provider,
            lane_key.account_ref,
            lane_key.model_ref,
            now,
            worker_ref,
            claim_ttl_seconds,
        )
        if row is None:
            return None
        return _claim_from_row(row)

    async def release_lane_claim(
        self,
        *,
        lane_id: str,
        worker_ref: str,
        now: datetime,
    ) -> None:
        await self._connection.execute(
            """
            UPDATE capacity_admission_lane_dirty_flags
            SET claimed_by = NULL,
                claimed_until = NULL,
                last_marked_at = GREATEST(last_marked_at, $3)
            WHERE lane_id = $1
              AND claimed_by = $2
            """,
            lane_id,
            worker_ref,
            now,
        )

    async def clear_dirty_flag(
        self,
        *,
        lane_id: str,
        worker_ref: str,
        now: datetime,
    ) -> None:
        await self._connection.execute(
            """
            DELETE FROM capacity_admission_lane_dirty_flags
            WHERE lane_id = $1
              AND claimed_by = $2
              AND last_marked_at <= $3
            """,
            lane_id,
            worker_ref,
            now,
        )


def _claim_from_row(row: Mapping[str, object]) -> CapacityLaneClaim:
    lane_key = CapacityAdmissionLaneKey(
        work_kind=_required_str(row, "work_kind"),
        provider=_required_str(row, "provider"),
        account_ref=_optional_str(row, "account_ref"),
        model_ref=_required_str(row, "model_ref"),
    )
    return CapacityLaneClaim(
        lane_id=_required_str(row, "lane_id"),
        lane_key=lane_key,
        claimed_by=_required_str(row, "claimed_by"),
        claimed_until=_required_datetime(row, "claimed_until"),
        claim_version=_required_positive_int(row, "claim_version"),
    )


def _lane_id(lane_key: CapacityAdmissionLaneKey) -> str:
    account_ref = lane_key.account_ref if lane_key.account_ref is not None else "-"
    return (
        f"{lane_key.work_kind}:{lane_key.provider}:{account_ref}:{lane_key.model_ref}"
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


def _required_datetime(row: Mapping[str, object], key: str) -> datetime:
    value = row.get(key)
    if not isinstance(value, datetime):
        raise ValueError(f"{key} must be datetime")
    return value


def _required_positive_int(row: Mapping[str, object], key: str) -> int:
    value = row.get(key)
    if not isinstance(value, int) or value <= 0:
        raise ValueError(f"{key} must be positive integer")
    return value
