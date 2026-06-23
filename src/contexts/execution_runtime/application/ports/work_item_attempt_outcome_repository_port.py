from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

from src.contexts.execution_runtime.domain.entities.work_item import WorkItem
from src.contexts.execution_runtime.domain.value_objects.lease_token import LeaseToken
from src.contexts.execution_runtime.domain.value_objects.work_item_retry_plan import (
    WorkItemRetryPlan,
)


class WorkItemAttemptOutcomeStatus(StrEnum):
    SUCCEEDED = "succeeded"
    RETRYABLE_FAILED = "retryable_failed"
    TERMINAL_FAILED = "terminal_failed"


@dataclass(frozen=True, slots=True)
class WorkItemAttemptOutcomeRecord:
    attempt_id: str
    work_item_id: str
    attempt_number: int
    lease_token: LeaseToken
    finished_at: datetime
    outcome_status: WorkItemAttemptOutcomeStatus
    error_kind: str | None = None
    retry_plan: WorkItemRetryPlan | None = None
    validation_metadata: Mapping[str, object] | None = None
    llm_output_payload: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.attempt_id, field_name="attempt_id")
        _require_non_empty_text(self.work_item_id, field_name="work_item_id")

        if not isinstance(self.attempt_number, int):
            raise TypeError("attempt_number must be int")
        if self.attempt_number <= 0:
            raise ValueError("attempt_number must be > 0")

        if not isinstance(self.lease_token, LeaseToken):
            raise TypeError("lease_token must be LeaseToken")

        _require_timezone_aware(self.finished_at, field_name="finished_at")

        if not isinstance(self.outcome_status, WorkItemAttemptOutcomeStatus):
            raise TypeError("outcome_status must be WorkItemAttemptOutcomeStatus")

        if self.retry_plan is not None and not isinstance(
            self.retry_plan,
            WorkItemRetryPlan,
        ):
            raise TypeError("retry_plan must be WorkItemRetryPlan when provided")

        if self.validation_metadata is not None and not isinstance(
            self.validation_metadata,
            Mapping,
        ):
            raise TypeError("validation_metadata must be Mapping when provided")
        if self.llm_output_payload is not None and not isinstance(
            self.llm_output_payload,
            Mapping,
        ):
            raise TypeError("llm_output_payload must be Mapping when provided")

        if self.outcome_status is WorkItemAttemptOutcomeStatus.SUCCEEDED:
            if self.error_kind is not None:
                raise ValueError("error_kind must be None for succeeded outcome")
            if self.retry_plan is not None:
                raise ValueError("retry_plan must be None for succeeded outcome")
            return

        if self.error_kind is None:
            raise ValueError("error_kind is required for failed outcomes")
        _require_non_empty_text(self.error_kind, field_name="error_kind")

        if self.outcome_status is WorkItemAttemptOutcomeStatus.TERMINAL_FAILED:
            if self.retry_plan is not None:
                raise ValueError(
                    "retry_plan must be None for terminal failed outcome",
                )
            return

        if self.outcome_status is WorkItemAttemptOutcomeStatus.RETRYABLE_FAILED:
            if self.retry_plan is None:
                raise ValueError(
                    "retry_plan is required for retryable outcomes",
                )
            return


@dataclass(frozen=True, slots=True)
class RecordedWorkItemAttemptOutcome:
    attempt_id: str
    work_item_id: str
    attempt_number: int
    finished_at: datetime
    outcome_status: WorkItemAttemptOutcomeStatus
    work_item: WorkItem
    error_kind: str | None = None
    retry_plan: WorkItemRetryPlan | None = None
    validation_metadata: Mapping[str, object] | None = None
    llm_output_payload: Mapping[str, object] | None = None

    def __post_init__(self) -> None:
        _require_non_empty_text(self.attempt_id, field_name="attempt_id")
        _require_non_empty_text(self.work_item_id, field_name="work_item_id")

        if not isinstance(self.attempt_number, int):
            raise TypeError("attempt_number must be int")
        if self.attempt_number <= 0:
            raise ValueError("attempt_number must be > 0")

        _require_timezone_aware(self.finished_at, field_name="finished_at")

        if not isinstance(self.outcome_status, WorkItemAttemptOutcomeStatus):
            raise TypeError("outcome_status must be WorkItemAttemptOutcomeStatus")

        if not isinstance(self.work_item, WorkItem):
            raise TypeError("work_item must be WorkItem")

        if self.validation_metadata is not None and not isinstance(
            self.validation_metadata,
            Mapping,
        ):
            raise TypeError("validation_metadata must be Mapping when provided")
        if self.llm_output_payload is not None and not isinstance(
            self.llm_output_payload,
            Mapping,
        ):
            raise TypeError("llm_output_payload must be Mapping when provided")

        if self.outcome_status is WorkItemAttemptOutcomeStatus.SUCCEEDED:
            if self.error_kind is not None:
                raise ValueError("error_kind must be None for succeeded outcome")
            if self.retry_plan is not None:
                raise ValueError("retry_plan must be None for succeeded outcome")
            return

        if self.error_kind is None:
            raise ValueError("error_kind is required for failed outcomes")
        _require_non_empty_text(self.error_kind, field_name="error_kind")

        if self.outcome_status is WorkItemAttemptOutcomeStatus.TERMINAL_FAILED:
            if self.retry_plan is not None:
                raise ValueError(
                    "retry_plan must be None for terminal failed outcome",
                )
            return


class WorkItemAttemptOutcomeRepositoryPort(Protocol):
    async def get_recorded_attempt_outcome(
        self,
        *,
        attempt_id: str,
    ) -> RecordedWorkItemAttemptOutcome | None: ...

    async def record_attempt_outcome(
        self,
        record: WorkItemAttemptOutcomeRecord,
    ) -> WorkItem: ...

    async def complete_work_item_after_domain_apply(
        self,
        *,
        work_item_id: str,
        lease_token: LeaseToken,
    ) -> WorkItem: ...


def _require_non_empty_text(value: str, *, field_name: str) -> None:
    if not isinstance(value, str):
        raise TypeError(f"{field_name} must be str")
    if not value.strip():
        raise ValueError(f"{field_name} must be non-empty")


def _require_timezone_aware(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
