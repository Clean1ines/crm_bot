from __future__ import annotations

import pytest

from src.domain.project_plane.llm_routing import (
    LlmInvocationFailure,
    LlmInvocationStatus,
    LlmJsonInvocationRequest,
    LlmJsonInvocationResult,
    LlmModelLimits,
    LlmModelProfile,
    LlmProvider,
    LlmRouteAttempt,
    LlmRouteAttemptStatus,
    LlmRoutePlan,
    LlmRoutingInvariantError,
    LlmTokenUsage,
)


def test_model_limits_validate_positive_values() -> None:
    limits = LlmModelLimits(
        requests_per_minute=30,
        tokens_per_minute=6000,
        requests_per_day=1000,
        tokens_per_day=100000,
        context_window_tokens=8192,
        max_output_tokens=2048,
        max_concurrent_requests=3,
    )

    assert limits.max_concurrent_requests == 3

    with pytest.raises(LlmRoutingInvariantError):
        LlmModelLimits(tokens_per_minute=0)


def test_provider_is_provider_agnostic_and_validates_identity() -> None:
    provider = LlmProvider(
        provider_id="provider-a",
        display_name="Provider A",
    )

    assert provider.provider_id == "provider-a"
    assert provider.enabled is True

    with pytest.raises(LlmRoutingInvariantError):
        LlmProvider(provider_id="", display_name="Custom")


def test_model_profile_contains_capabilities_and_limits() -> None:
    profile = LlmModelProfile(
        provider_id="provider-a",
        model="llama-3.1-8b-instant",
        display_name="Llama 3.1 8B Instant",
        limits=LlmModelLimits(max_output_tokens=8192, max_concurrent_requests=3),
        supports_json_object=True,
    )

    assert profile.supports_json_object is True
    assert profile.limits.max_output_tokens == 8192


def test_route_plan_requires_contiguous_attempt_indexes() -> None:
    attempt_0 = LlmRouteAttempt(
        provider_id="provider-a",
        model="llama-3.1-8b-instant",
        api_key_slot="key-slot-1",
        attempt_index=0,
    )
    attempt_1 = LlmRouteAttempt(
        provider_id="provider-a",
        model="llama-3.3-70b-versatile",
        api_key_slot="key-slot-2",
        attempt_index=1,
    )

    plan = LlmRoutePlan(
        route_chain_id="faq-claim-observations",
        operation_name="faq_surface_claim_observations",
        attempts=(attempt_0, attempt_1),
    )

    assert plan.route_chain == (
        "provider-a:llama-3.1-8b-instant:key-slot-1",
        "provider-a:llama-3.3-70b-versatile:key-slot-2",
    )

    with pytest.raises(ValueError):
        LlmRoutePlan(
            route_chain_id="bad",
            operation_name="bad",
            attempts=(
                LlmRouteAttempt(
                    provider_id="provider-a",
                    model="a",
                    api_key_slot="slot",
                    attempt_index=1,
                ),
            ),
        )


def test_json_invocation_request_requires_prompt_and_operation() -> None:
    request = LlmJsonInvocationRequest(
        operation_name="faq_surface_claim_observations",
        prompt="Return JSON",
        route_purpose="workbench_claim_observations",
    )

    assert request.operation_name == "faq_surface_claim_observations"

    with pytest.raises(LlmRoutingInvariantError):
        LlmJsonInvocationRequest(
            operation_name="",
            prompt="Return JSON",
            route_purpose="workbench_claim_observations",
        )


def test_successful_json_invocation_requires_parsed_json() -> None:
    attempt = LlmRouteAttempt(
        provider_id="provider-a",
        model="llama-3.1-8b-instant",
        api_key_slot="key-slot-1",
        attempt_index=0,
        status=LlmRouteAttemptStatus.SUCCESS,
    )

    result = LlmJsonInvocationResult(
        status=LlmInvocationStatus.SUCCESS,
        parsed_json={"findings": []},
        raw_text='{"findings":[]}',
        token_usage=LlmTokenUsage(prompt_tokens=10, completion_tokens=5),
        attempts=(attempt,),
    )

    assert result.token_usage.total_tokens == 15

    with pytest.raises(ValueError):
        LlmJsonInvocationResult(
            status=LlmInvocationStatus.SUCCESS,
            parsed_json=None,
            raw_text="",
            token_usage=LlmTokenUsage(prompt_tokens=0, completion_tokens=0),
            attempts=(attempt,),
        )


def test_failed_invocation_requires_failure() -> None:
    attempt = LlmRouteAttempt(
        provider_id="provider-a",
        model="llama-3.1-8b-instant",
        api_key_slot="key-slot-1",
        attempt_index=0,
        status=LlmRouteAttemptStatus.FAILED,
        error_kind="rpm",
        cooldown_seconds=60,
    )

    failure = LlmInvocationFailure(
        status=LlmInvocationStatus.RATE_LIMITED,
        error_kind="rpm",
        user_message="Provider is rate limited.",
        internal_message="RPM exceeded",
        cooldown_seconds=60,
    )

    result = LlmJsonInvocationResult(
        status=LlmInvocationStatus.RATE_LIMITED,
        parsed_json=None,
        raw_text="",
        token_usage=LlmTokenUsage(prompt_tokens=10, completion_tokens=0),
        attempts=(attempt,),
        failure=failure,
    )

    assert result.failure == failure

    with pytest.raises(ValueError):
        LlmJsonInvocationResult(
            status=LlmInvocationStatus.RATE_LIMITED,
            parsed_json=None,
            raw_text="",
            token_usage=LlmTokenUsage(prompt_tokens=10, completion_tokens=0),
            attempts=(attempt,),
            failure=None,
        )
