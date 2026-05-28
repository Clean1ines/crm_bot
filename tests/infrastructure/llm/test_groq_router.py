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


def test_select_chain_uses_primary_models_by_default() -> None:
    router = GroqModelRouter()

    chain_name, models = router.select_chain(
        requested_model=None,
        kwargs={"messages": [{"role": "user", "content": "short"}]},
    )

    assert chain_name.value == "primary_chain"
    assert models == PRIMARY_CHAIN


def test_select_chain_uses_large_request_chain_for_big_prompt() -> None:
    router = GroqModelRouter()

    chain_name, models = router.select_chain(
        requested_model=None,
        kwargs={"messages": [{"role": "user", "content": "x" * 13_000}]},
    )

    assert chain_name.value == "large_request_chain"
    assert models == LARGE_REQUEST_CHAIN


def test_select_chain_uses_cheap_chain_for_requested_small_model() -> None:
    router = GroqModelRouter()

    chain_name, models = router.select_chain(
        requested_model="llama-3.1-8b-instant",
        kwargs={"messages": [{"role": "user", "content": "short"}]},
    )

    assert chain_name.value == "cheap_small_chain"
    assert models == CHEAP_SMALL_CHAIN


@pytest.mark.asyncio
async def test_router_falls_back_to_next_model_on_request_too_large() -> None:
    calls: list[str] = []
    router = GroqModelRouter(
        GroqFallbackPolicy(
            primary_chain=("small-model", "large-model"),
            large_request_chain=("large-model",),
            cheap_small_chain=("small-model",),
            max_attempts_per_call=4,
            max_attempts_per_model=2,
            max_elapsed_seconds_per_call=10.0,
            base_backoff_seconds=0.0,
        )
    )

    async def create_call(kwargs: dict[str, object]) -> str:
        model = str(kwargs["model"])
        calls.append(model)
        if model == "small-model":
            raise ProviderError("request too large for model", status_code=413)
        return "ok"

    result = await router.run_chat_completion(
        create_call=create_call,
        kwargs={
            "model": "small-model",
            "messages": [{"role": "user", "content": "short"}],
        },
        operation_name="test",
    )

    assert result == "ok"
    assert calls == ["small-model", "large-model"]


@pytest.mark.asyncio
async def test_router_raises_quota_exhausted_after_all_daily_routes_fail() -> None:
    router = GroqModelRouter(
        GroqFallbackPolicy(
            primary_chain=("first", "second"),
            large_request_chain=("first", "second"),
            cheap_small_chain=("first",),
            max_attempts_per_call=4,
            max_attempts_per_model=2,
            max_elapsed_seconds_per_call=10.0,
            base_backoff_seconds=0.0,
        )
    )

    async def create_call(kwargs: dict[str, object]) -> str:
        raise ProviderError("daily tokens per day quota exhausted", status_code=429)

    with pytest.raises(GroqFallbackExhaustedError) as exc_info:
        await router.run_chat_completion(
            create_call=create_call,
            kwargs={
                "model": "first",
                "messages": [{"role": "user", "content": "short"}],
            },
            operation_name="test",
        )

    assert exc_info.value.failure_type == GroqRouteFailureType.QUOTA_EXHAUSTED


@pytest.mark.asyncio
async def test_router_hard_caps_transient_retries() -> None:
    calls = 0
    router = GroqModelRouter(
        GroqFallbackPolicy(
            primary_chain=("first", "second"),
            large_request_chain=("first", "second"),
            cheap_small_chain=("first",),
            max_attempts_per_call=3,
            max_attempts_per_model=2,
            max_elapsed_seconds_per_call=10.0,
            base_backoff_seconds=0.0,
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
