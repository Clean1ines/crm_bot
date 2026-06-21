from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

import pytest

from src.contexts.execution_runtime.domain.value_objects.work_item_status import (
    WorkItemStatus,
)
from src.contexts.execution_runtime.domain.value_objects.work_kind import WorkKind
from src.contexts.knowledge_workbench.extraction.infrastructure.postgres.postgres_claim_builder_retry_action_read_repository import (
    PostgresClaimBuilderRetryActionReadRepository,
)
from src.contexts.knowledge_workbench.extraction.application.policies.claim_builder_attempt_next_action_policy import (
    ClaimBuilderAttemptNextActionKind,
)


def _now() -> datetime:
    return datetime(2026, 6, 12, 12, 0, tzinfo=UTC)


def _workflow_run_id() -> str:
    return "knowledge-extraction:source-document:project-1:abc"


def _work_kind() -> WorkKind:
    return WorkKind("knowledge_workbench.claim_builder.section_extraction")


@dataclass(frozen=True, slots=True)
class FakeRetryActionRow:
    work_item_id: str
    status: WorkItemStatus
    action_kind: ClaimBuilderAttemptNextActionKind
    next_model_strategy: str | None = None
    requires_source_split: bool = False
    next_run_after: datetime | None = None

    def to_payload(self) -> dict[str, object]:
        return {
            "work_kind": _work_kind().value,
            "work_item_id": self.work_item_id,
            "dispatch_attempt_id": f"{self.work_item_id}:attempt:1",
            "claim_builder_attempt_next_action_kind": self.action_kind.value,
            "claim_builder_attempt_next_model_strategy": self.next_model_strategy,
            "claim_builder_requires_source_split": self.requires_source_split,
            "claim_builder_next_run_after": (
                self.next_run_after.isoformat()
                if self.next_run_after is not None
                else None
            ),
        }


@dataclass(slots=True)
class FakeConnection:
    rows: tuple[FakeRetryActionRow, ...]
    last_query: str | None = None
    last_workflow_run_id: str | None = None
    last_work_kind: str | None = None
    last_action_values: list[str] | None = None
    last_status_values: list[str] | None = None

    async def fetch(
        self,
        query: str,
        workflow_run_id: str,
        work_kind: str,
        action_values: list[str],
        status_values: list[str],
    ) -> list[dict[str, object]]:
        self.last_query = query
        self.last_workflow_run_id = workflow_run_id
        self.last_work_kind = work_kind
        self.last_action_values = action_values
        self.last_status_values = status_values

        return [
            {"payload": row.to_payload()}
            for row in self.rows
            if row.status.value in status_values
            and row.action_kind.value in action_values
        ]


async def _summarize(
    rows: tuple[FakeRetryActionRow, ...],
):
    connection = FakeConnection(rows=rows)
    repository = PostgresClaimBuilderRetryActionReadRepository(connection)

    summary = await repository.summarize_retry_actions(
        workflow_run_id=_workflow_run_id(),
        work_kind=_work_kind(),
        now=_now(),
    )
    return summary, connection


@pytest.mark.asyncio
async def test_retry_action_for_retryable_failed_work_item_is_counted() -> None:
    summary, connection = await _summarize(
        (
            FakeRetryActionRow(
                work_item_id="work-1",
                status=WorkItemStatus.RETRYABLE_FAILED,
                action_kind=ClaimBuilderAttemptNextActionKind.RETRY_FALLBACK_MODEL,
                next_model_strategy="FALLBACK_MODEL_REQUIRED",
            ),
        )
    )

    assert summary.retry_fallback_model_count == 1
    assert summary.retry_empty_claims_check_model_count == 0
    assert summary.retry_larger_output_limit_route_count == 0
    assert connection.last_status_values == [
        WorkItemStatus.READY.value,
        WorkItemStatus.LEASED.value,
        WorkItemStatus.RETRYABLE_FAILED.value,
    ]
    assert connection.last_query is not None
    assert "JOIN execution_work_items wi" in connection.last_query
    assert "wi.status = ANY($4::text[])" in connection.last_query


@pytest.mark.asyncio
async def test_retry_action_for_legacy_deferred_work_item_is_ignored() -> None:
    summary, _ = await _summarize(
        (
            FakeRetryActionRow(
                work_item_id="work-1",
                status=WorkItemStatus.DEFERRED,
                action_kind=ClaimBuilderAttemptNextActionKind.RETRY_SAME_ROUTE,
                next_model_strategy="SAME_MODEL",
            ),
        )
    )

    assert summary.retry_same_route_count == 0
    assert summary.records == ()


@pytest.mark.asyncio
async def test_retry_action_for_completed_work_item_is_ignored() -> None:
    summary, _ = await _summarize(
        (
            FakeRetryActionRow(
                work_item_id="work-1",
                status=WorkItemStatus.COMPLETED,
                action_kind=(
                    ClaimBuilderAttemptNextActionKind.RETRY_LARGER_OUTPUT_LIMIT_MODEL
                ),
                next_model_strategy="LARGER_OUTPUT_LIMIT_MODEL_REQUIRED",
            ),
        )
    )

    assert summary.retry_larger_output_limit_route_count == 0
    assert summary.records == ()


@pytest.mark.asyncio
async def test_retry_action_for_terminal_failed_work_item_is_ignored() -> None:
    summary, _ = await _summarize(
        (
            FakeRetryActionRow(
                work_item_id="work-1",
                status=WorkItemStatus.TERMINAL_FAILED,
                action_kind=ClaimBuilderAttemptNextActionKind.RETRY_FALLBACK_MODEL,
                next_model_strategy="FALLBACK_MODEL_REQUIRED",
            ),
        )
    )

    assert summary.retry_fallback_model_count == 0
    assert summary.records == ()


@pytest.mark.asyncio
async def test_mixed_stale_larger_output_and_current_fallback_selects_current_only() -> (
    None
):
    summary, _ = await _summarize(
        (
            FakeRetryActionRow(
                work_item_id="stale-work",
                status=WorkItemStatus.COMPLETED,
                action_kind=(
                    ClaimBuilderAttemptNextActionKind.RETRY_LARGER_OUTPUT_LIMIT_MODEL
                ),
                next_model_strategy="LARGER_OUTPUT_LIMIT_MODEL_REQUIRED",
            ),
            FakeRetryActionRow(
                work_item_id="current-work",
                status=WorkItemStatus.RETRYABLE_FAILED,
                action_kind=ClaimBuilderAttemptNextActionKind.RETRY_FALLBACK_MODEL,
                next_model_strategy="FALLBACK_MODEL_REQUIRED",
            ),
        )
    )

    assert summary.retry_larger_output_limit_route_count == 0
    assert summary.retry_fallback_model_count == 1
    assert tuple(record.work_item_id for record in summary.records) == ("current-work",)
