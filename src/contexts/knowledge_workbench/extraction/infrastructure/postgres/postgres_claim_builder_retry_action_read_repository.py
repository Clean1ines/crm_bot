from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

import asyncpg

from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.extraction.application.ports.claim_builder_retry_action_read_repository_port import (
    ClaimBuilderRetryActionReadRepositoryPort,
    WorkItemRetryActionRecord,
    WorkItemRetryActionSummary,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_attempt_next_action_policy import (
    ClaimBuilderAttemptNextActionKind,
)


class PostgresClaimBuilderRetryActionReadRepository(
    ClaimBuilderRetryActionReadRepositoryPort
):
    def __init__(self, connection: asyncpg.Connection) -> None:
        self._connection = connection

    async def summarize_retry_actions(
        self,
        *,
        workflow_run_id: str,
        work_kind: WorkKind,
        now: datetime,
    ) -> WorkItemRetryActionSummary:
        if not workflow_run_id.strip():
            raise ValueError("workflow_run_id must be non-empty")
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("now must be timezone-aware")

        rows = await self._connection.fetch(
            """
            WITH latest_retry_action AS (
                SELECT DISTINCT ON (payload->>'work_item_id')
                    payload,
                    occurred_at,
                    sequence_number
                FROM workflow_runtime_outbox_events
                WHERE workflow_run_id = $1
                  AND payload->>'work_kind' = $2
                  AND payload ? 'claim_builder_attempt_next_action_kind'
                  AND payload->>'claim_builder_attempt_next_action_kind' = ANY($3::text[])
                ORDER BY
                    payload->>'work_item_id',
                    occurred_at DESC,
                    sequence_number DESC
            )
            SELECT payload
            FROM latest_retry_action
            ORDER BY sequence_number ASC
            """,
            workflow_run_id,
            work_kind.value,
            _retry_action_values(),
        )

        records = tuple(_record_from_row(row) for row in rows)
        return _summary_from_records(
            workflow_run_id=workflow_run_id,
            work_kind=work_kind,
            records=records,
            now=now,
        )


def _retry_action_values() -> list[str]:
    return [
        ClaimBuilderAttemptNextActionKind.RETRY_SAME_MODEL.value,
        ClaimBuilderAttemptNextActionKind.RETRY_FALLBACK_MODEL.value,
        ClaimBuilderAttemptNextActionKind.RETRY_LARGER_OUTPUT_LIMIT_MODEL.value,
        ClaimBuilderAttemptNextActionKind.SPLIT_SOURCE_UNIT.value,
        ClaimBuilderAttemptNextActionKind.DEFER_UNTIL_CAPACITY_RESET.value,
    ]


def _record_from_row(row: Mapping[str, object]) -> WorkItemRetryActionRecord:
    payload = row["payload"]
    if not isinstance(payload, Mapping):
        raise TypeError("payload must be mapping")

    return WorkItemRetryActionRecord(
        work_item_id=_required_text(payload, "work_item_id"),
        dispatch_attempt_id=_required_text(payload, "dispatch_attempt_id"),
        next_action_kind=_required_text(
            payload,
            "claim_builder_attempt_next_action_kind",
        ),
        next_model_strategy=_optional_text(
            payload,
            "claim_builder_attempt_next_model_strategy",
        ),
        requires_source_split=_required_bool(
            payload,
            "claim_builder_requires_source_split",
        ),
        next_run_after=_optional_datetime_text(
            payload,
            "claim_builder_next_run_after",
        ),
    )


def _summary_from_records(
    *,
    workflow_run_id: str,
    work_kind: WorkKind,
    records: tuple[WorkItemRetryActionRecord, ...],
    now: datetime,
) -> WorkItemRetryActionSummary:
    retry_same_model_count = 0
    retry_fallback_model_count = 0
    retry_larger_output_model_count = 0
    split_required_count = 0
    defer_until_capacity_reset_count = 0
    future_run_afters: list[datetime] = []

    for record in records:
        if (
            record.next_action_kind
            == ClaimBuilderAttemptNextActionKind.RETRY_SAME_MODEL.value
        ):
            retry_same_model_count += 1
        elif (
            record.next_action_kind
            == ClaimBuilderAttemptNextActionKind.RETRY_FALLBACK_MODEL.value
        ):
            retry_fallback_model_count += 1
        elif (
            record.next_action_kind
            == ClaimBuilderAttemptNextActionKind.RETRY_LARGER_OUTPUT_LIMIT_MODEL.value
        ):
            retry_larger_output_model_count += 1
        elif (
            record.next_action_kind
            == ClaimBuilderAttemptNextActionKind.SPLIT_SOURCE_UNIT.value
        ):
            split_required_count += 1
        elif (
            record.next_action_kind
            == ClaimBuilderAttemptNextActionKind.DEFER_UNTIL_CAPACITY_RESET.value
        ):
            defer_until_capacity_reset_count += 1

        if record.next_run_after is not None and record.next_run_after > now:
            future_run_afters.append(record.next_run_after)

    return WorkItemRetryActionSummary(
        workflow_run_id=workflow_run_id,
        work_kind=work_kind,
        retry_same_model_count=retry_same_model_count,
        retry_fallback_model_count=retry_fallback_model_count,
        retry_larger_output_model_count=retry_larger_output_model_count,
        split_required_count=split_required_count,
        defer_until_capacity_reset_count=defer_until_capacity_reset_count,
        next_run_after=min(future_run_afters) if future_run_afters else None,
        records=records,
    )


def _required_text(payload: Mapping[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be non-empty text")
    return value


def _optional_text(payload: Mapping[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be null or non-empty text")
    return value


def _required_bool(payload: Mapping[str, object], key: str) -> bool:
    value = payload.get(key)
    if not isinstance(value, bool):
        raise TypeError(f"{key} must be bool")
    return value


def _optional_datetime_text(payload: Mapping[str, object], key: str) -> datetime | None:
    value = payload.get(key)
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{key} must be null or non-empty datetime text")
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{key} must be timezone-aware")
    return parsed
