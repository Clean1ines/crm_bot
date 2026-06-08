from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from src.contexts.llm_runtime.application.policies.llm_route_planning_policy import (
    LlmRouteCandidate,
    LlmRoutePlanDecisionKind,
    LlmRoutePlanningPolicy,
)
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind
from src.contexts.llm_runtime.domain.value_objects.llm_route import LlmRoute
from src.contexts.llm_runtime.domain.value_objects.model_id import ModelId
from src.contexts.llm_runtime.domain.value_objects.provider_account_ref import (
    ProviderAccountRef,
)
from src.contexts.llm_runtime.domain.value_objects.provider_id import ProviderId


def _now() -> datetime:
    return datetime(2026, 6, 8, 12, 0, tzinfo=timezone.utc)


def _route(model: str, account: str) -> LlmRoute:
    return LlmRoute(
        provider_id=ProviderId("provider"),
        model_id=ModelId(model),
        account_ref=ProviderAccountRef(account),
    )


def _candidate(
    *,
    model: str,
    account: str,
    context_window_tokens: int,
    max_output_tokens: int,
    model_rank: int,
    account_rank: int,
    minute_capacity_available: bool = True,
    daily_capacity_available: bool = True,
    unavailable_until: datetime | None = None,
) -> LlmRouteCandidate:
    return LlmRouteCandidate(
        route=_route(model, account),
        context_window_tokens=context_window_tokens,
        max_output_tokens=max_output_tokens,
        model_rank=model_rank,
        account_rank=account_rank,
        minute_capacity_available=minute_capacity_available,
        daily_capacity_available=daily_capacity_available,
        unavailable_until=unavailable_until,
    )


def test_request_too_large_prefers_larger_context_model_on_same_account() -> None:
    current = _candidate(
        model="model-small",
        account="account-1",
        context_window_tokens=8_000,
        max_output_tokens=2_000,
        model_rank=0,
        account_rank=0,
    )
    larger_same_account = _candidate(
        model="model-large",
        account="account-1",
        context_window_tokens=32_000,
        max_output_tokens=2_000,
        model_rank=1,
        account_rank=0,
    )
    larger_other_account = _candidate(
        model="model-large",
        account="account-2",
        context_window_tokens=32_000,
        max_output_tokens=2_000,
        model_rank=1,
        account_rank=1,
    )

    decision = LlmRoutePlanningPolicy().decide(
        LlmErrorKind.REQUEST_TOO_LARGE,
        current_route=current.route,
        candidates=(current, larger_other_account, larger_same_account),
    )

    assert decision.kind is LlmRoutePlanDecisionKind.USE_ROUTE
    assert decision.route == larger_same_account.route


def test_request_too_large_requires_split_when_no_larger_context_route_exists() -> None:
    current = _candidate(
        model="model-small",
        account="account-1",
        context_window_tokens=8_000,
        max_output_tokens=2_000,
        model_rank=0,
        account_rank=0,
    )

    decision = LlmRoutePlanningPolicy().decide(
        LlmErrorKind.REQUEST_TOO_LARGE,
        current_route=current.route,
        candidates=(current,),
    )

    assert decision.kind is LlmRoutePlanDecisionKind.SPLIT_REQUIRED


def test_output_too_large_prefers_larger_output_route() -> None:
    current = _candidate(
        model="model-small-output",
        account="account-1",
        context_window_tokens=8_000,
        max_output_tokens=1_000,
        model_rank=0,
        account_rank=0,
    )
    larger_output = _candidate(
        model="model-large-output",
        account="account-1",
        context_window_tokens=8_000,
        max_output_tokens=4_000,
        model_rank=1,
        account_rank=0,
    )

    decision = LlmRoutePlanningPolicy().decide(
        LlmErrorKind.OUTPUT_TOO_LARGE,
        current_route=current.route,
        candidates=(current, larger_output),
    )

    assert decision.kind is LlmRoutePlanDecisionKind.USE_ROUTE
    assert decision.route == larger_output.route


def test_minute_limit_prefers_same_model_on_other_available_account() -> None:
    current = _candidate(
        model="model-1",
        account="account-1",
        context_window_tokens=8_000,
        max_output_tokens=2_000,
        model_rank=0,
        account_rank=0,
        minute_capacity_available=False,
        unavailable_until=_now() + timedelta(seconds=60),
    )
    same_model_other_account = _candidate(
        model="model-1",
        account="account-2",
        context_window_tokens=8_000,
        max_output_tokens=2_000,
        model_rank=0,
        account_rank=1,
    )
    other_model = _candidate(
        model="model-2",
        account="account-1",
        context_window_tokens=32_000,
        max_output_tokens=2_000,
        model_rank=1,
        account_rank=0,
    )

    decision = LlmRoutePlanningPolicy().decide(
        LlmErrorKind.MINUTE_LIMIT,
        current_route=current.route,
        candidates=(current, other_model, same_model_other_account),
    )

    assert decision.kind is LlmRoutePlanDecisionKind.USE_ROUTE
    assert decision.route == same_model_other_account.route


def test_minute_limit_waits_for_nearest_unavailable_route_when_no_account_available() -> (
    None
):
    first_wait = _now() + timedelta(seconds=60)
    second_wait = _now() + timedelta(seconds=120)
    current = _candidate(
        model="model-1",
        account="account-1",
        context_window_tokens=8_000,
        max_output_tokens=2_000,
        model_rank=0,
        account_rank=0,
        minute_capacity_available=False,
        unavailable_until=second_wait,
    )
    other_account = _candidate(
        model="model-1",
        account="account-2",
        context_window_tokens=8_000,
        max_output_tokens=2_000,
        model_rank=0,
        account_rank=1,
        minute_capacity_available=False,
        unavailable_until=first_wait,
    )

    decision = LlmRoutePlanningPolicy().decide(
        LlmErrorKind.MINUTE_LIMIT,
        current_route=current.route,
        candidates=(current, other_account),
    )

    assert decision.kind is LlmRoutePlanDecisionKind.WAIT_UNTIL
    assert decision.wait_until == first_wait


def test_daily_limit_prefers_same_model_other_account_then_other_model() -> None:
    current = _candidate(
        model="model-1",
        account="account-1",
        context_window_tokens=8_000,
        max_output_tokens=2_000,
        model_rank=0,
        account_rank=0,
        daily_capacity_available=False,
    )
    same_model_other_account = _candidate(
        model="model-1",
        account="account-2",
        context_window_tokens=8_000,
        max_output_tokens=2_000,
        model_rank=0,
        account_rank=1,
    )
    other_model = _candidate(
        model="model-2",
        account="account-1",
        context_window_tokens=32_000,
        max_output_tokens=2_000,
        model_rank=1,
        account_rank=0,
    )

    first_decision = LlmRoutePlanningPolicy().decide(
        LlmErrorKind.DAILY_LIMIT,
        current_route=current.route,
        candidates=(current, other_model, same_model_other_account),
    )

    assert first_decision.kind is LlmRoutePlanDecisionKind.USE_ROUTE
    assert first_decision.route == same_model_other_account.route

    exhausted_same_model = _candidate(
        model="model-1",
        account="account-2",
        context_window_tokens=8_000,
        max_output_tokens=2_000,
        model_rank=0,
        account_rank=1,
        daily_capacity_available=False,
    )

    second_decision = LlmRoutePlanningPolicy().decide(
        LlmErrorKind.DAILY_LIMIT,
        current_route=current.route,
        candidates=(current, exhausted_same_model, other_model),
    )

    assert second_decision.kind is LlmRoutePlanDecisionKind.USE_ROUTE
    assert second_decision.route == other_model.route


def test_daily_limit_reports_exhausted_when_no_route_available() -> None:
    current = _candidate(
        model="model-1",
        account="account-1",
        context_window_tokens=8_000,
        max_output_tokens=2_000,
        model_rank=0,
        account_rank=0,
        daily_capacity_available=False,
    )
    other = _candidate(
        model="model-2",
        account="account-1",
        context_window_tokens=32_000,
        max_output_tokens=2_000,
        model_rank=1,
        account_rank=0,
        daily_capacity_available=False,
    )

    decision = LlmRoutePlanningPolicy().decide(
        LlmErrorKind.DAILY_LIMIT,
        current_route=current.route,
        candidates=(current, other),
    )

    assert decision.kind is LlmRoutePlanDecisionKind.DAILY_EXHAUSTED


def test_network_and_validation_errors_do_not_change_route_at_route_planning_layer() -> (
    None
):
    current = _candidate(
        model="model-1",
        account="account-1",
        context_window_tokens=8_000,
        max_output_tokens=2_000,
        model_rank=0,
        account_rank=0,
    )

    for error_kind in (
        LlmErrorKind.NETWORK_ERROR,
        LlmErrorKind.UNKNOWN,
        LlmErrorKind.INVALID_OUTPUT,
        LlmErrorKind.VALIDATION_FAILED,
        LlmErrorKind.EMPTY_OUTPUT,
    ):
        decision = LlmRoutePlanningPolicy().decide(
            error_kind,
            current_route=current.route,
            candidates=(current,),
        )

        assert decision.kind is LlmRoutePlanDecisionKind.RETRY_SAME_ROUTE


def test_auth_error_is_terminal_at_route_planning_layer() -> None:
    current = _candidate(
        model="model-1",
        account="account-1",
        context_window_tokens=8_000,
        max_output_tokens=2_000,
        model_rank=0,
        account_rank=0,
    )

    decision = LlmRoutePlanningPolicy().decide(
        LlmErrorKind.AUTH_ERROR,
        current_route=current.route,
        candidates=(current,),
    )

    assert decision.kind is LlmRoutePlanDecisionKind.TERMINAL_FAILURE


def test_current_route_must_be_present_in_candidates() -> None:
    current = _candidate(
        model="model-1",
        account="account-1",
        context_window_tokens=8_000,
        max_output_tokens=2_000,
        model_rank=0,
        account_rank=0,
    )
    other = _candidate(
        model="model-2",
        account="account-1",
        context_window_tokens=32_000,
        max_output_tokens=2_000,
        model_rank=1,
        account_rank=0,
    )

    with pytest.raises(ValueError):
        LlmRoutePlanningPolicy().decide(
            LlmErrorKind.REQUEST_TOO_LARGE,
            current_route=current.route,
            candidates=(other,),
        )
