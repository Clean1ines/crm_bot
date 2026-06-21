from __future__ import annotations

from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.jsonb_payload_hydration import (
    hydrate_jsonb_object_payload,
)
from collections.abc import Mapping
from datetime import datetime

import asyncpg

from src.contexts.execution_runtime.domain.value_objects.work_item_retry_plan import (
    WorkItemRetryPlan,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
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
            SELECT lra.payload
            FROM latest_retry_action lra
            JOIN execution_work_items wi
              ON wi.work_item_id = lra.payload->>'work_item_id'
            WHERE wi.status = ANY($4::text[])
            ORDER BY lra.sequence_number ASC
            """,
            workflow_run_id,
            work_kind.value,
            _retry_action_values(),
            _automatic_retry_status_values(),
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
        ClaimBuilderAttemptNextActionKind.RETRY_SAME_ROUTE.value,
        ClaimBuilderAttemptNextActionKind.RETRY_EMPTY_CLAIMS_CHECK_MODEL.value,
        ClaimBuilderAttemptNextActionKind.RETRY_FALLBACK_MODEL.value,
        ClaimBuilderAttemptNextActionKind.RETRY_LARGER_OUTPUT_LIMIT_MODEL.value,
        ClaimBuilderAttemptNextActionKind.RETRY_LARGER_INPUT_LIMIT_MODEL.value,
        ClaimBuilderAttemptNextActionKind.SPLIT_WORK_PAYLOAD.value,
        ClaimBuilderAttemptNextActionKind.DEFER_UNTIL_CAPACITY_RESET.value,
        ClaimBuilderAttemptNextActionKind.PAUSE_FOR_DAILY_LIMIT_RESET.value,
        ClaimBuilderAttemptNextActionKind.REQUEST_USER_LOW_QUALITY_CONTINUE_OR_WAIT.value,
    ]


def _automatic_retry_status_values() -> list[str]:
    return [
        WorkItemStatus.READY.value,
        WorkItemStatus.LEASED.value,
        WorkItemStatus.RETRYABLE_FAILED.value,
    ]


def _record_from_row(row: Mapping[str, object]) -> WorkItemRetryActionRecord:
    payload = hydrate_jsonb_object_payload(
        row["payload"],
        field_name="workflow_runtime_outbox_events.payload",
    )

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
        retry_plan=_retry_plan_from_next_action_payload(payload),
    )


def _summary_from_records(
    *,
    workflow_run_id: str,
    work_kind: WorkKind,
    records: tuple[WorkItemRetryActionRecord, ...],
    now: datetime,
) -> WorkItemRetryActionSummary:
    retry_same_route_count = 0
    retry_empty_claims_check_model_count = 0
    retry_fallback_model_count = 0
    retry_larger_output_limit_route_count = 0
    retry_larger_input_model_count = 0
    split_required_count = 0
    defer_until_capacity_reset_count = 0
    pause_for_daily_limit_reset_count = 0
    request_user_low_quality_continue_or_wait_count = 0
    future_run_afters: list[datetime] = []

    for record in records:
        if (
            record.next_action_kind
            == ClaimBuilderAttemptNextActionKind.RETRY_SAME_ROUTE.value
        ):
            retry_same_route_count += 1
        elif (
            record.next_action_kind
            == ClaimBuilderAttemptNextActionKind.RETRY_EMPTY_CLAIMS_CHECK_MODEL.value
        ):
            retry_empty_claims_check_model_count += 1
        elif (
            record.next_action_kind
            == ClaimBuilderAttemptNextActionKind.RETRY_FALLBACK_MODEL.value
        ):
            retry_fallback_model_count += 1
        elif (
            record.next_action_kind
            == ClaimBuilderAttemptNextActionKind.RETRY_LARGER_OUTPUT_LIMIT_MODEL.value
        ):
            retry_larger_output_limit_route_count += 1
        elif (
            record.next_action_kind
            == ClaimBuilderAttemptNextActionKind.RETRY_LARGER_INPUT_LIMIT_MODEL.value
        ):
            retry_larger_input_model_count += 1
        elif (
            record.next_action_kind
            == ClaimBuilderAttemptNextActionKind.SPLIT_WORK_PAYLOAD.value
        ):
            split_required_count += 1
        elif (
            record.next_action_kind
            == ClaimBuilderAttemptNextActionKind.DEFER_UNTIL_CAPACITY_RESET.value
        ):
            defer_until_capacity_reset_count += 1
        elif (
            record.next_action_kind
            == ClaimBuilderAttemptNextActionKind.PAUSE_FOR_DAILY_LIMIT_RESET.value
        ):
            pause_for_daily_limit_reset_count += 1
        elif (
            record.next_action_kind
            == ClaimBuilderAttemptNextActionKind.REQUEST_USER_LOW_QUALITY_CONTINUE_OR_WAIT.value
        ):
            request_user_low_quality_continue_or_wait_count += 1

        if record.next_run_after is not None and record.next_run_after > now:
            future_run_afters.append(record.next_run_after)

    return WorkItemRetryActionSummary(
        workflow_run_id=workflow_run_id,
        work_kind=work_kind,
        retry_same_route_count=retry_same_route_count,
        retry_empty_claims_check_model_count=retry_empty_claims_check_model_count,
        retry_fallback_model_count=retry_fallback_model_count,
        retry_larger_output_limit_route_count=retry_larger_output_limit_route_count,
        retry_larger_input_model_count=retry_larger_input_model_count,
        split_required_count=split_required_count,
        defer_until_capacity_reset_count=defer_until_capacity_reset_count,
        pause_for_daily_limit_reset_count=pause_for_daily_limit_reset_count,
        request_user_low_quality_continue_or_wait_count=(
            request_user_low_quality_continue_or_wait_count
        ),
        next_run_after=min(future_run_afters) if future_run_afters else None,
        selected_retry_plan=_selected_retry_plan_from_records(records),
        records=records,
    )


def _retry_plan_from_next_action_payload(
    payload: Mapping[str, object],
) -> WorkItemRetryPlan | None:
    next_action_kind = _required_text(
        payload,
        "claim_builder_attempt_next_action_kind",
    )

    if next_action_kind == ClaimBuilderAttemptNextActionKind.RETRY_SAME_ROUTE.value:
        return WorkItemRetryPlan.RETRY_SAME_ROUTE
    if (
        next_action_kind
        == ClaimBuilderAttemptNextActionKind.RETRY_EMPTY_CLAIMS_CHECK_MODEL.value
    ):
        return WorkItemRetryPlan.RETRY_VALIDATION_CHECK_ROUTE
    if (
        next_action_kind
        == ClaimBuilderAttemptNextActionKind.RETRY_LARGER_OUTPUT_LIMIT_MODEL.value
    ):
        return WorkItemRetryPlan.RETRY_LARGER_OUTPUT_LIMIT_ROUTE
    if (
        next_action_kind
        == ClaimBuilderAttemptNextActionKind.RETRY_LARGER_INPUT_LIMIT_MODEL.value
    ):
        return WorkItemRetryPlan.RETRY_LARGER_INPUT_LIMIT_ROUTE
    if (
        next_action_kind
        == ClaimBuilderAttemptNextActionKind.DEFER_UNTIL_CAPACITY_RESET.value
    ):
        return WorkItemRetryPlan.WAIT_NEAREST_ADMISSION_WINDOW
    if (
        next_action_kind
        == ClaimBuilderAttemptNextActionKind.PAUSE_FOR_DAILY_LIMIT_RESET.value
    ):
        return WorkItemRetryPlan.WAIT_DAILY_ADMISSION_RESET
    if next_action_kind == ClaimBuilderAttemptNextActionKind.RETRY_FALLBACK_MODEL.value:
        next_model_strategy = _optional_text(
            payload,
            "claim_builder_attempt_next_model_strategy",
        )
        if next_model_strategy == "DAILY_LIMIT_FALLBACK_MODEL_REQUIRED":
            return WorkItemRetryPlan.RETRY_DAILY_FALLBACK_ROUTE
        return WorkItemRetryPlan.RETRY_DAILY_FALLBACK_ROUTE

    return None


def _selected_retry_plan_from_records(
    records: tuple[WorkItemRetryActionRecord, ...],
) -> WorkItemRetryPlan | None:
    priority = (
        WorkItemRetryPlan.RETRY_LARGER_INPUT_LIMIT_ROUTE,
        WorkItemRetryPlan.RETRY_LARGER_OUTPUT_LIMIT_ROUTE,
        WorkItemRetryPlan.RETRY_DAILY_FALLBACK_ROUTE,
        WorkItemRetryPlan.RETRY_VALIDATION_CHECK_ROUTE,
        WorkItemRetryPlan.WAIT_NEAREST_ADMISSION_WINDOW,
        WorkItemRetryPlan.RETRY_SAME_ROUTE,
    )
    available = {
        record.retry_plan for record in records if record.retry_plan is not None
    }
    for retry_plan in priority:
        if retry_plan in available:
            return retry_plan
    return None


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
