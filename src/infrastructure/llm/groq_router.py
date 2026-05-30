from __future__ import annotations

import asyncio
import re
from collections.abc import Awaitable, Callable, Iterable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypeVar

from src.infrastructure.logging.logger import get_logger

logger = get_logger(__name__)

ResultT = TypeVar("ResultT")

GROQ_MODEL_LLAMA_4_SCOUT = "meta-llama/llama-4-scout-17b-16e-instruct"
GROQ_MODEL_LLAMA_33_70B = "llama-3.3-70b-versatile"
GROQ_MODEL_QWEN3_32B = "qwen/qwen3-32b"
GROQ_MODEL_GPT_OSS_120B = "openai/gpt-oss-120b"
GROQ_MODEL_GPT_OSS_20B = "openai/gpt-oss-20b"
GROQ_MODEL_LLAMA_31_8B = "llama-3.1-8b-instant"

PRIMARY_CHAIN: tuple[str, ...] = (
    GROQ_MODEL_LLAMA_31_8B,
    GROQ_MODEL_QWEN3_32B,
    GROQ_MODEL_GPT_OSS_20B,
    GROQ_MODEL_LLAMA_4_SCOUT,
    GROQ_MODEL_LLAMA_33_70B,
    GROQ_MODEL_GPT_OSS_120B,
)

LARGE_REQUEST_CHAIN: tuple[str, ...] = (
    GROQ_MODEL_LLAMA_4_SCOUT,
    GROQ_MODEL_LLAMA_33_70B,
    GROQ_MODEL_GPT_OSS_120B,
    GROQ_MODEL_QWEN3_32B,
)

CHEAP_SMALL_CHAIN: tuple[str, ...] = (
    GROQ_MODEL_LLAMA_31_8B,
    GROQ_MODEL_QWEN3_32B,
    GROQ_MODEL_GPT_OSS_20B,
)

# Known relative completion capacity order only.
# This is not an output-token prediction and not a task-kind budget table.
# Provider errors remain the source of truth; this order is used only after
# the provider explicitly reports a max-completion/output-size failure.
KNOWN_COMPLETION_CAPACITY_ASC: tuple[str, ...] = (
    GROQ_MODEL_LLAMA_31_8B,
    GROQ_MODEL_GPT_OSS_20B,
    GROQ_MODEL_QWEN3_32B,
    GROQ_MODEL_LLAMA_4_SCOUT,
    GROQ_MODEL_LLAMA_33_70B,
    GROQ_MODEL_GPT_OSS_120B,
)

DISALLOWED_COMPILER_MODELS: frozenset[str] = frozenset(
    {
        "meta-llama/llama-prompt-guard-2-22m",
        "meta-llama/llama-prompt-guard-2-86m",
        "openai/gpt-oss-safeguard-20b",
        "canopylabs/orpheus-v1-english",
        "groq/compound",
        "groq/compound-mini",
    }
)


class GroqLimitKind(StrEnum):
    NONE = "none"
    REQUEST_TOO_LARGE = "request_too_large"
    CONTEXT_LIMIT = "context_limit"
    OUTPUT_TOO_LARGE = "output_too_large"
    TPM = "tpm"
    RPM = "rpm"
    TPD = "tpd"
    RPD = "rpd"
    RATE_LIMIT = "rate_limit"
    TEMPORARY_PROVIDER_ERROR = "temporary_provider_error"


class GroqRouteFailureType(StrEnum):
    INPUT_TOO_LARGE = "input_too_large"
    OUTPUT_TOO_LARGE = "output_too_large"
    QUOTA_EXHAUSTED = "groq_quota_exhausted"
    ALL_FALLBACKS_EXHAUSTED = "all_fallbacks_exhausted"


class GroqRouteChain(StrEnum):
    PRIMARY = "primary_chain"
    LARGE_REQUEST = "large_request_chain"
    CHEAP_SMALL = "cheap_small_chain"


@dataclass(frozen=True, slots=True)
class GroqFallbackPolicy:
    primary_chain: tuple[str, ...] = PRIMARY_CHAIN
    large_request_chain: tuple[str, ...] = LARGE_REQUEST_CHAIN
    cheap_small_chain: tuple[str, ...] = CHEAP_SMALL_CHAIN
    max_attempts_per_call: int = 24
    max_attempts_per_model: int = 1
    max_elapsed_seconds_per_call: float = 240.0
    base_backoff_seconds: float = 0.25
    default_rate_limit_cooldown_seconds: float = 60.0
    max_rate_limit_sleep_seconds: float = 65.0


@dataclass(frozen=True, slots=True)
class GroqRouteAttempt:
    model: str
    chain: GroqRouteChain
    attempt_index: int
    total_attempt_index: int
    fallback_reason: GroqLimitKind


@dataclass(frozen=True, slots=True)
class GroqRouteState:
    model: str
    cooldown_until: float | None = None
    daily_exhausted: bool = False
    unsuitable_for_payload: bool = False

    def is_cooling_down(self, *, now: float) -> bool:
        return self.cooldown_until is not None and self.cooldown_until > now

    def is_available(self, *, now: float) -> bool:
        return (
            not self.daily_exhausted
            and not self.unsuitable_for_payload
            and not self.is_cooling_down(now=now)
        )


class GroqFallbackExhaustedError(RuntimeError):
    def __init__(
        self,
        *,
        failure_type: GroqRouteFailureType,
        message: str,
        last_error: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.failure_type = failure_type
        self.last_error = last_error


def _exception_text(exc: BaseException) -> str:
    response = getattr(exc, "response", None)
    response_text = getattr(response, "text", None)
    if response_text:
        return f"{exc} {response_text}".lower()
    return str(exc).lower()


def _exception_status_code(exc: BaseException) -> int | None:
    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int):
        return status_code
    response = getattr(exc, "response", None)
    response_status_code = getattr(response, "status_code", None)
    if isinstance(response_status_code, int):
        return response_status_code
    return None


def classify_groq_exception(exc: BaseException) -> GroqLimitKind:
    status_code = _exception_status_code(exc)
    text = _exception_text(exc)
    type_name = type(exc).__name__.lower()

    if status_code == 429 or "ratelimit" in type_name:
        if "tokens per day" in text or "tpd" in text or "daily token" in text:
            return GroqLimitKind.TPD
        if "requests per day" in text or "rpd" in text or "daily request" in text:
            return GroqLimitKind.RPD
        if "quota exhausted" in text or "daily quota" in text:
            return GroqLimitKind.TPD
        if "tokens per minute" in text or "tpm" in text:
            return GroqLimitKind.TPM
        if "requests per minute" in text or "rpm" in text:
            return GroqLimitKind.RPM
        return GroqLimitKind.RATE_LIMIT

    output_too_large_markers = (
        "max_completion_tokens",
        "max completion tokens",
        "maximum completion",
        "completion limit",
        "completion tokens limit",
        "output too large",
        "output tokens",
        "generated output",
        "response too large",
        "reduce max_tokens",
        "reduce max tokens",
        "max_tokens is too large",
        "max tokens is too large",
    )
    if any(marker in text for marker in output_too_large_markers):
        return GroqLimitKind.OUTPUT_TOO_LARGE

    request_too_large_markers = (
        "request too large",
        "request_too_large",
        "too large for model",
        "payload too large",
        "maximum context length",
        "context length",
        "context_limit",
        "context window",
        "reduce the length",
    )
    if status_code == 413 or any(
        marker in text for marker in request_too_large_markers
    ):
        if "context" in text:
            return GroqLimitKind.CONTEXT_LIMIT
        return GroqLimitKind.REQUEST_TOO_LARGE

    temporary_markers = (
        "timeout",
        "temporarily unavailable",
        "connection",
        "server error",
        "service unavailable",
    )
    if status_code is not None and status_code >= 500:
        return GroqLimitKind.TEMPORARY_PROVIDER_ERROR
    if any(marker in text or marker in type_name for marker in temporary_markers):
        return GroqLimitKind.TEMPORARY_PROVIDER_ERROR

    return GroqLimitKind.NONE


def is_minute_groq_limit(kind: GroqLimitKind) -> bool:
    return kind in {GroqLimitKind.TPM, GroqLimitKind.RPM, GroqLimitKind.RATE_LIMIT}


def is_transient_groq_limit(kind: GroqLimitKind) -> bool:
    return kind in {
        GroqLimitKind.TPM,
        GroqLimitKind.RPM,
        GroqLimitKind.RATE_LIMIT,
        GroqLimitKind.TEMPORARY_PROVIDER_ERROR,
    }


def is_daily_groq_quota(kind: GroqLimitKind) -> bool:
    return kind in {GroqLimitKind.TPD, GroqLimitKind.RPD}


def is_groq_input_too_large(kind: GroqLimitKind) -> bool:
    return kind in {GroqLimitKind.REQUEST_TOO_LARGE, GroqLimitKind.CONTEXT_LIMIT}


def is_groq_output_too_large(kind: GroqLimitKind) -> bool:
    return kind == GroqLimitKind.OUTPUT_TOO_LARGE


def _completion_capacity_rank(model: str) -> int:
    try:
        return KNOWN_COMPLETION_CAPACITY_ASC.index(model)
    except ValueError:
        return -1


def _larger_completion_capacity_models(
    *,
    current_model: str,
    candidates: Iterable[str],
) -> tuple[str, ...]:
    current_rank = _completion_capacity_rank(current_model)
    if current_rank < 0:
        return ()
    ordered = tuple(
        model
        for model in KNOWN_COMPLETION_CAPACITY_ASC
        if _completion_capacity_rank(model) > current_rank and model in set(candidates)
    )
    return _dedupe_models(ordered)


def _dedupe_models(models: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for model in models:
        if not model or model in seen or model in DISALLOWED_COMPILER_MODELS:
            continue
        result.append(model)
        seen.add(model)
    return tuple(result)


def _is_large_request(kwargs: Mapping[str, object]) -> bool:
    # Provider response is the source of truth.
    # Every compiler request starts with llama-3.1-8b-instant.
    return False


_RETRY_AFTER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"retry(?:\s|-)?after\D+(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"try again in\D+(\d+(?:\.\d+)?)", re.IGNORECASE),
    re.compile(r"please try again in\D+(\d+(?:\.\d+)?)", re.IGNORECASE),
)


def retry_after_seconds_from_exception(exc: BaseException) -> float | None:
    retry_after = getattr(exc, "retry_after", None)
    if isinstance(retry_after, int | float) and retry_after > 0:
        return float(retry_after)

    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if headers is not None:
        header_value = None
        get_header = getattr(headers, "get", None)
        if callable(get_header):
            header_value = get_header("retry-after") or get_header("Retry-After")
        if header_value is not None:
            try:
                parsed = float(str(header_value))
            except ValueError:
                parsed = 0.0
            if parsed > 0:
                return parsed

    text = _exception_text(exc)
    for pattern in _RETRY_AFTER_PATTERNS:
        match = pattern.search(text)
        if match:
            try:
                parsed = float(match.group(1))
            except ValueError:
                continue
            if parsed > 0:
                return parsed
    return None


@dataclass(slots=True)
class _RouteStateStore:
    models: list[str]
    states: dict[str, GroqRouteState] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for model in self.models:
            self.states.setdefault(model, GroqRouteState(model=model))

    def append_models(self, models: Iterable[str]) -> None:
        for model in models:
            if model in self.states or model in DISALLOWED_COMPILER_MODELS:
                continue
            self.models.append(model)
            self.states[model] = GroqRouteState(model=model)

    def next_available_model(self, *, now: float) -> str | None:
        for model in self.models:
            state = self.states[model]
            if state.is_available(now=now):
                return model
        return None

    def nearest_cooldown_until(self, *, now: float) -> float | None:
        cooldowns = [
            state.cooldown_until
            for state in self.states.values()
            if state.cooldown_until is not None
            and state.cooldown_until > now
            and not state.daily_exhausted
            and not state.unsuitable_for_payload
        ]
        if not cooldowns:
            return None
        return min(cooldowns)

    def has_non_daily_routes(self) -> bool:
        return any(not state.daily_exhausted for state in self.states.values())

    def mark_unsuitable_for_payload(self, model: str) -> None:
        state = self.states[model]
        self.states[model] = GroqRouteState(
            model=model,
            cooldown_until=state.cooldown_until,
            daily_exhausted=state.daily_exhausted,
            unsuitable_for_payload=True,
        )

    def mark_unsuitable_for_output(self, model: str) -> None:
        self.mark_unsuitable_for_payload(model)

    def mark_daily_exhausted(self, model: str) -> None:
        state = self.states[model]
        self.states[model] = GroqRouteState(
            model=model,
            cooldown_until=state.cooldown_until,
            daily_exhausted=True,
            unsuitable_for_payload=state.unsuitable_for_payload,
        )

    def mark_cooldown(self, model: str, *, cooldown_until: float) -> None:
        state = self.states[model]
        self.states[model] = GroqRouteState(
            model=model,
            cooldown_until=cooldown_until,
            daily_exhausted=state.daily_exhausted,
            unsuitable_for_payload=state.unsuitable_for_payload,
        )

    def clear_expired_cooldowns(self, *, now: float) -> None:
        for model, state in list(self.states.items()):
            if state.cooldown_until is not None and state.cooldown_until <= now:
                self.states[model] = GroqRouteState(
                    model=model,
                    cooldown_until=None,
                    daily_exhausted=state.daily_exhausted,
                    unsuitable_for_payload=state.unsuitable_for_payload,
                )


class GroqModelRouter:
    def __init__(self, policy: GroqFallbackPolicy | None = None) -> None:
        self._policy = policy or GroqFallbackPolicy()

    def select_chain(
        self,
        *,
        requested_model: str | None,
        kwargs: Mapping[str, object],
    ) -> tuple[GroqRouteChain, tuple[str, ...]]:
        # Hard invariant: every compiler request starts with the weak/cheap
        # instant-first chain. requested_model is never allowed to jump ahead.
        if requested_model in DISALLOWED_COMPILER_MODELS:
            requested_model = None

        chain_name = GroqRouteChain.CHEAP_SMALL
        chain = self._policy.cheap_small_chain
        if requested_model and requested_model not in chain:
            return chain_name, _dedupe_models(
                (*chain, requested_model, *self._policy.primary_chain)
            )
        return chain_name, _dedupe_models((*chain, *self._policy.primary_chain))

    async def run_chat_completion(
        self,
        *,
        create_call: Callable[[dict[str, object]], Awaitable[ResultT]],
        kwargs: Mapping[str, object],
        operation_name: str,
    ) -> ResultT:
        requested_model = kwargs.get("model")
        requested_model_text = (
            requested_model if isinstance(requested_model, str) else None
        )
        chain_name, selected_models = self.select_chain(
            requested_model=requested_model_text,
            kwargs=kwargs,
        )
        store = _RouteStateStore(models=list(selected_models))
        if not store.models:
            raise GroqFallbackExhaustedError(
                failure_type=GroqRouteFailureType.ALL_FALLBACKS_EXHAUSTED,
                message="No Groq fallback models are available for this call",
            )

        loop = asyncio.get_running_loop()
        started_at = loop.time()
        total_attempts = 0
        per_model_attempts: dict[str, int] = {}
        last_error: BaseException | None = None
        last_limit_kind = GroqLimitKind.NONE

        while True:
            now = loop.time()
            elapsed = now - started_at
            store.clear_expired_cooldowns(now=now)

            if total_attempts >= self._policy.max_attempts_per_call:
                raise self._exhausted_error(
                    last_limit_kind=last_limit_kind,
                    last_error=last_error,
                    reason="max attempts per call exhausted",
                )
            if elapsed >= self._policy.max_elapsed_seconds_per_call:
                raise self._exhausted_error(
                    last_limit_kind=last_limit_kind,
                    last_error=last_error,
                    reason="max elapsed seconds per call exhausted",
                )

            model = store.next_available_model(now=now)
            if model is None:
                cooldown_until = store.nearest_cooldown_until(now=now)
                if cooldown_until is not None and store.has_non_daily_routes():
                    sleep_seconds = min(
                        max(cooldown_until - now, 0.0),
                        self._policy.max_rate_limit_sleep_seconds,
                    )
                    if sleep_seconds > 0:
                        logger.warning(
                            "All Groq routes are cooling down; waiting for rate-limit reset",
                            extra={
                                "operation": operation_name,
                                "sleep_seconds": round(sleep_seconds, 3),
                                "last_limit_kind": last_limit_kind.value,
                            },
                        )
                        await asyncio.sleep(sleep_seconds)
                        continue

                raise self._exhausted_error(
                    last_limit_kind=last_limit_kind,
                    last_error=last_error,
                    reason="all fallback models exhausted",
                )

            per_model_attempts[model] = per_model_attempts.get(model, 0) + 1
            model_attempts = per_model_attempts[model]

            total_attempts += 1
            attempt = GroqRouteAttempt(
                model=model,
                chain=chain_name,
                attempt_index=model_attempts,
                total_attempt_index=total_attempts,
                fallback_reason=last_limit_kind,
            )

            routed_kwargs = dict(kwargs)
            routed_kwargs["model"] = model

            try:
                self._log_attempt(operation_name=operation_name, attempt=attempt)
                return await create_call(routed_kwargs)
            except Exception as exc:
                last_error = exc
                last_limit_kind = classify_groq_exception(exc)

                if last_limit_kind == GroqLimitKind.NONE:
                    raise

                if is_groq_input_too_large(last_limit_kind):
                    store.mark_unsuitable_for_payload(model)
                    store.append_models(self._policy.large_request_chain)
                    logger.warning(
                        "Groq model rejected request size; trying large-capable fallback models",
                        extra={
                            "operation": operation_name,
                            "model": model,
                            "limit_kind": last_limit_kind.value,
                            "chain": chain_name.value,
                        },
                    )
                    continue

                if is_groq_output_too_large(last_limit_kind):
                    store.mark_unsuitable_for_output(model)
                    larger_models = _larger_completion_capacity_models(
                        current_model=model,
                        candidates=(
                            *self._policy.cheap_small_chain,
                            *self._policy.primary_chain,
                            *self._policy.large_request_chain,
                        ),
                    )
                    store.append_models(larger_models)
                    logger.warning(
                        "Groq model rejected completion size; trying larger known completion-capacity routes",
                        extra={
                            "operation": operation_name,
                            "model": model,
                            "limit_kind": last_limit_kind.value,
                            "chain": chain_name.value,
                            "larger_completion_capacity_route_count": len(
                                larger_models
                            ),
                        },
                    )
                    continue

                if is_daily_groq_quota(last_limit_kind):
                    store.mark_daily_exhausted(model)
                    logger.warning(
                        "Groq daily quota exhausted for route; disabling route for this call",
                        extra={
                            "operation": operation_name,
                            "model": model,
                            "limit_kind": last_limit_kind.value,
                            "chain": chain_name.value,
                        },
                    )
                    continue

                if is_minute_groq_limit(last_limit_kind):
                    retry_after = retry_after_seconds_from_exception(exc)
                    cooldown_seconds = (
                        retry_after
                        if retry_after is not None
                        else self._policy.default_rate_limit_cooldown_seconds
                    )
                    store.mark_cooldown(
                        model,
                        cooldown_until=loop.time() + max(cooldown_seconds, 0.0),
                    )
                    logger.warning(
                        "Groq minute rate limit hit for route; cooling route and trying another model",
                        extra={
                            "operation": operation_name,
                            "model": model,
                            "limit_kind": last_limit_kind.value,
                            "chain": chain_name.value,
                            "cooldown_seconds": round(cooldown_seconds, 3),
                        },
                    )
                    continue

                if last_limit_kind == GroqLimitKind.TEMPORARY_PROVIDER_ERROR:
                    if model_attempts < self._policy.max_attempts_per_model:
                        await self._bounded_backoff(total_attempts=total_attempts)
                        continue
                    store.mark_cooldown(
                        model,
                        cooldown_until=loop.time() + self._policy.base_backoff_seconds,
                    )
                    continue

                raise

    async def _bounded_backoff(self, *, total_attempts: int) -> None:
        delay = min(
            self._policy.base_backoff_seconds * max(total_attempts, 1),
            2.0,
        )
        if delay > 0:
            await asyncio.sleep(delay)

    def _exhausted_error(
        self,
        *,
        last_limit_kind: GroqLimitKind,
        last_error: BaseException | None,
        reason: str,
    ) -> GroqFallbackExhaustedError:
        if is_groq_input_too_large(last_limit_kind):
            failure_type = GroqRouteFailureType.INPUT_TOO_LARGE
        elif is_groq_output_too_large(last_limit_kind):
            failure_type = GroqRouteFailureType.OUTPUT_TOO_LARGE
        elif is_daily_groq_quota(last_limit_kind):
            failure_type = GroqRouteFailureType.QUOTA_EXHAUSTED
        else:
            failure_type = GroqRouteFailureType.ALL_FALLBACKS_EXHAUSTED
        return GroqFallbackExhaustedError(
            failure_type=failure_type,
            message=f"Groq fallback routing failed: {reason}: {failure_type.value}",
            last_error=last_error,
        )

    @staticmethod
    def _log_attempt(*, operation_name: str, attempt: GroqRouteAttempt) -> None:
        logger.info(
            "Groq route attempt",
            extra={
                "operation": operation_name,
                "model": attempt.model,
                "chain": attempt.chain.value,
                "attempt_index": attempt.attempt_index,
                "total_attempt_index": attempt.total_attempt_index,
                "fallback_reason": attempt.fallback_reason.value,
            },
        )
