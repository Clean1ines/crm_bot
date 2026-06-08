from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.llm_runtime.application.policies.llm_error_policy import (
    LlmErrorDisposition,
    LlmErrorDispositionKind,
    LlmErrorPolicy,
)
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def test_minute_limit_is_deferred_until_given_timestamp() -> None:
    wait_until = _now() + timedelta(seconds=60)

    disposition = LlmErrorPolicy().decide(
        LlmErrorKind.MINUTE_LIMIT,
        wait_until=wait_until,
    )

    assert disposition.kind is LlmErrorDispositionKind.DEFER_UNTIL
    assert disposition.error_kind is LlmErrorKind.MINUTE_LIMIT
    assert disposition.wait_until == wait_until


def test_minute_limit_requires_wait_until() -> None:
    with pytest.raises(ValueError):
        LlmErrorPolicy().decide(LlmErrorKind.MINUTE_LIMIT)


def test_oversized_and_daily_limit_try_alternate_route() -> None:
    policy = LlmErrorPolicy()

    for error_kind in (
        LlmErrorKind.REQUEST_TOO_LARGE,
        LlmErrorKind.OUTPUT_TOO_LARGE,
        LlmErrorKind.DAILY_LIMIT,
    ):
        disposition = policy.decide(error_kind)
        assert disposition.kind is LlmErrorDispositionKind.TRY_ALTERNATE_ROUTE
        assert disposition.error_kind is error_kind


def test_invalid_outputs_use_validation_retry() -> None:
    policy = LlmErrorPolicy()

    for error_kind in (
        LlmErrorKind.INVALID_OUTPUT,
        LlmErrorKind.VALIDATION_FAILED,
    ):
        disposition = policy.decide(error_kind)
        assert disposition.kind is LlmErrorDispositionKind.VALIDATION_RETRY
        assert disposition.error_kind is error_kind


def test_empty_output_requires_confirmation_path() -> None:
    disposition = LlmErrorPolicy().decide(LlmErrorKind.EMPTY_OUTPUT)

    assert disposition.kind is LlmErrorDispositionKind.CONFIRM_EMPTY_OUTPUT
    assert disposition.error_kind is LlmErrorKind.EMPTY_OUTPUT


def test_auth_error_is_terminal_failure() -> None:
    disposition = LlmErrorPolicy().decide(LlmErrorKind.AUTH_ERROR)

    assert disposition.kind is LlmErrorDispositionKind.TERMINAL_FAILURE
    assert disposition.error_kind is LlmErrorKind.AUTH_ERROR


def test_network_and_unknown_errors_retry_same_route() -> None:
    policy = LlmErrorPolicy()

    for error_kind in (
        LlmErrorKind.NETWORK_ERROR,
        LlmErrorKind.UNKNOWN,
    ):
        disposition = policy.decide(error_kind)
        assert disposition.kind is LlmErrorDispositionKind.RETRY_SAME_ROUTE
        assert disposition.error_kind is error_kind


def test_only_defer_until_can_carry_wait_until() -> None:
    with pytest.raises(ValueError):
        LlmErrorDisposition(
            kind=LlmErrorDispositionKind.RETRY_SAME_ROUTE,
            error_kind=LlmErrorKind.NETWORK_ERROR,
            wait_until=_now(),
        )

    with pytest.raises(ValueError):
        LlmErrorDisposition(
            kind=LlmErrorDispositionKind.DEFER_UNTIL,
            error_kind=LlmErrorKind.MINUTE_LIMIT,
            wait_until=datetime(2026, 6, 8, 12, 0),
        )
