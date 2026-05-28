from __future__ import annotations

import pytest

from src.infrastructure.llm.groq_router import (
    CHEAP_SMALL_CHAIN,
    LARGE_REQUEST_CHAIN,
    PRIMARY_CHAIN,
    GroqFallbackExhaustedError,
    GroqFallbackPolicy,
    GroqLimitKind,
    GroqModelRouter,
    GroqRouteFailureType,
    classify_groq_exception,
)


class ProviderError(Exception):
    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code


@pytest.mark.parametrize(
    ("message", "status_code", "expected"),
    [
        ("rate limit exceeded: tokens per minute", 429, GroqLimitKind.TPM),
        ("rate limit exceeded: requests per minute", 429, GroqLimitKind.RPM),
        ("daily tokens per day quota exhausted", 429, GroqLimitKind.TPD),
        ("daily requests per day quota exhausted", 429, GroqLimitKind.RPD),
        ("request too large for model", 413, GroqLimitKind.REQUEST_TOO_LARGE),
        ("maximum context length exceeded", 400, GroqLimitKind.CONTEXT_LIMIT),
        ("service unavailable", 503, GroqLimitKind.TEMPORARY_PROVIDER_ERROR),
    ],
)
def test_classify_groq_exception_distinguishes_limit_types(
    message: str,
    status_code: int,
    expected: GroqLimitKind,
) -> None:
    assert (
        classify_groq_exception(ProviderError(message, status_code=status_code))
        == expected
    )


def test_select_chain_uses_instant_first_models_by_default() -> None:
    router = GroqModelRouter()

    chain_name, models = router.select_chain(
        requested_model=None,
        kwargs={"messages": [{"role": "user", "content": "short"}]},
    )

    assert chain_name.value == "cheap_small_chain"
    assert models[0] == "llama-3.1-8b-instant"
    assert models == PRIMARY_CHAIN


def test_large_request_chain_is_not_selected_by_prompt_guess() -> None:
    router = GroqModelRouter()

    chain_name, models = router.select_chain(
        requested_model=None,
        kwargs={"messages": [{"role": "user", "content": "x" * 13_000}]},
    )

    assert chain_name.value == "cheap_small_chain"
    assert models[0] == "llama-3.1-8b-instant"
    assert models != LARGE_REQUEST_CHAIN


def test_max_tokens_does_not_select_large_request_chain() -> None:
    router = GroqModelRouter()

    chain_name, models = router.select_chain(
        requested_model=None,
        kwargs={
            "messages": [{"role": "user", "content": "short"}],
            "max_tokens": 6000,
        },
    )

    assert chain_name.value == "cheap_small_chain"
    assert models[0] == "llama-3.1-8b-instant"
    assert models != LARGE_REQUEST_CHAIN


def test_select_chain_always_starts_with_instant_even_when_scout_requested() -> None:
    router = GroqModelRouter()

    chain_name, models = router.select_chain(
        requested_model="meta-llama/llama-4-scout-17b-16e-instruct",
        kwargs={
            "messages": [{"role": "user", "content": "short"}],
            "max_tokens": 6000,
        },
    )

    assert chain_name.value == "cheap_small_chain"
    assert models[0] == "llama-3.1-8b-instant"
    assert "meta-llama/llama-4-scout-17b-16e-instruct" in models


def test_select_chain_uses_cheap_prefix_for_requested_small_model() -> None:
    router = GroqModelRouter()

    chain_name, models = router.select_chain(
        requested_model="llama-3.1-8b-instant",
        kwargs={"messages": [{"role": "user", "content": "short"}]},
    )

    assert chain_name.value == "cheap_small_chain"
    assert models[: len(CHEAP_SMALL_CHAIN)] == CHEAP_SMALL_CHAIN


@pytest.mark.asyncio
async def test_router_first_attempt_is_instant_for_any_requested_model() -> None:
    calls: list[str] = []
    router = GroqModelRouter(
        GroqFallbackPolicy(
            primary_chain=(
                "llama-3.1-8b-instant",
                "qwen/qwen3-32b",
                "openai/gpt-oss-20b",
                "meta-llama/llama-4-scout-17b-16e-instruct",
            ),
            large_request_chain=("meta-llama/llama-4-scout-17b-16e-instruct",),
            cheap_small_chain=(
                "llama-3.1-8b-instant",
                "qwen/qwen3-32b",
                "openai/gpt-oss-20b",
            ),
            max_attempts_per_call=4,
            max_attempts_per_model=1,
            max_elapsed_seconds_per_call=10.0,
            base_backoff_seconds=0.0,
        )
    )

    async def create_call(kwargs: dict[str, object]) -> str:
        calls.append(str(kwargs["model"]))
        return "ok"

    result = await router.run_chat_completion(
        create_call=create_call,
        kwargs={
            "model": "meta-llama/llama-4-scout-17b-16e-instruct",
            "messages": [{"role": "user", "content": "short"}],
            "max_tokens": 6000,
        },
        operation_name="test",
    )

    assert result == "ok"
    assert calls == ["llama-3.1-8b-instant"]


@pytest.mark.asyncio
async def test_context_too_large_escalates_to_large_models_without_waiting() -> None:
    calls: list[str] = []
    router = GroqModelRouter(
        GroqFallbackPolicy(
            primary_chain=("instant", "qwen", "small-oss"),
            large_request_chain=("large-a", "large-b"),
            cheap_small_chain=("instant", "qwen", "small-oss"),
            max_attempts_per_call=8,
            max_attempts_per_model=1,
            max_elapsed_seconds_per_call=10.0,
            base_backoff_seconds=0.0,
        )
    )

    async def create_call(kwargs: dict[str, object]) -> str:
        model = str(kwargs["model"])
        calls.append(model)
        if model in {"instant", "qwen", "small-oss"}:
            raise ProviderError("maximum context length exceeded", status_code=400)
        return "ok"

    result = await router.run_chat_completion(
        create_call=create_call,
        kwargs={"messages": [{"role": "user", "content": "short"}]},
        operation_name="test",
    )

    assert result == "ok"
    assert calls == ["instant", "qwen", "small-oss", "large-a"]


@pytest.mark.asyncio
async def test_tpm_goes_to_next_models_then_waits_for_reset() -> None:
    calls: list[str] = []
    router = GroqModelRouter(
        GroqFallbackPolicy(
            primary_chain=("instant", "qwen"),
            large_request_chain=("large",),
            cheap_small_chain=("instant", "qwen"),
            max_attempts_per_call=4,
            max_attempts_per_model=1,
            max_elapsed_seconds_per_call=10.0,
            base_backoff_seconds=0.0,
            default_rate_limit_cooldown_seconds=0.01,
            max_rate_limit_sleep_seconds=0.02,
        )
    )

    async def create_call(kwargs: dict[str, object]) -> str:
        model = str(kwargs["model"])
        calls.append(model)
        if len(calls) <= 2:
            raise ProviderError("tokens per minute exceeded", status_code=429)
        return "ok"

    result = await router.run_chat_completion(
        create_call=create_call,
        kwargs={"messages": [{"role": "user", "content": "short"}]},
        operation_name="test",
    )

    assert result == "ok"
    assert calls == ["instant", "qwen", "instant"]


@pytest.mark.asyncio
async def test_tpd_disables_route_and_tries_other_model() -> None:
    calls: list[str] = []
    router = GroqModelRouter(
        GroqFallbackPolicy(
            primary_chain=("instant", "qwen"),
            large_request_chain=("large",),
            cheap_small_chain=("instant", "qwen"),
            max_attempts_per_call=4,
            max_attempts_per_model=1,
            max_elapsed_seconds_per_call=10.0,
            base_backoff_seconds=0.0,
        )
    )

    async def create_call(kwargs: dict[str, object]) -> str:
        model = str(kwargs["model"])
        calls.append(model)
        if model == "instant":
            raise ProviderError("daily tokens per day quota exhausted", status_code=429)
        return "ok"

    result = await router.run_chat_completion(
        create_call=create_call,
        kwargs={"messages": [{"role": "user", "content": "short"}]},
        operation_name="test",
    )

    assert result == "ok"
    assert calls == ["instant", "qwen"]


@pytest.mark.asyncio
async def test_daily_quota_exhaustion_reports_quota_exhausted() -> None:
    router = GroqModelRouter(
        GroqFallbackPolicy(
            primary_chain=("instant", "qwen"),
            large_request_chain=("large",),
            cheap_small_chain=("instant", "qwen"),
            max_attempts_per_call=4,
            max_attempts_per_model=1,
            max_elapsed_seconds_per_call=10.0,
            base_backoff_seconds=0.0,
        )
    )

    async def create_call(kwargs: dict[str, object]) -> str:
        raise ProviderError("daily tokens per day quota exhausted", status_code=429)

    with pytest.raises(GroqFallbackExhaustedError) as exc_info:
        await router.run_chat_completion(
            create_call=create_call,
            kwargs={"messages": [{"role": "user", "content": "short"}]},
            operation_name="test",
        )

    assert exc_info.value.failure_type == GroqRouteFailureType.QUOTA_EXHAUSTED


@pytest.mark.asyncio
async def test_tpm_hard_caps_after_repeated_minute_resets() -> None:
    calls = 0
    router = GroqModelRouter(
        GroqFallbackPolicy(
            primary_chain=("instant", "qwen"),
            large_request_chain=("large",),
            cheap_small_chain=("instant", "qwen"),
            max_attempts_per_call=3,
            max_attempts_per_model=1,
            max_elapsed_seconds_per_call=10.0,
            base_backoff_seconds=0.0,
            default_rate_limit_cooldown_seconds=0.01,
            max_rate_limit_sleep_seconds=0.02,
        )
    )

    async def create_call(kwargs: dict[str, object]) -> str:
        nonlocal calls
        calls += 1
        raise ProviderError("tokens per minute exceeded", status_code=429)

    with pytest.raises(GroqFallbackExhaustedError) as exc_info:
        await router.run_chat_completion(
            create_call=create_call,
            kwargs={"messages": [{"role": "user", "content": "short"}]},
            operation_name="test",
        )

    assert calls == 3
    assert exc_info.value.failure_type == GroqRouteFailureType.ALL_FALLBACKS_EXHAUSTED
