from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
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
    GROQ_MODEL_LLAMA_4_SCOUT,
    GROQ_MODEL_LLAMA_33_70B,
    GROQ_MODEL_QWEN3_32B,
    GROQ_MODEL_GPT_OSS_120B,
    GROQ_MODEL_GPT_OSS_20B,
    GROQ_MODEL_LLAMA_31_8B,
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
    TPM = "tpm"
    RPM = "rpm"
    TPD = "tpd"
    RATE_LIMIT = "rate_limit"
    TEMPORARY_PROVIDER_ERROR = "temporary_provider_error"


class GroqRouteFailureType(StrEnum):
    INPUT_TOO_LARGE = "input_too_large"
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
    max_attempts_per_call: int = 8
    max_attempts_per_model: int = 2
    max_elapsed_seconds_per_call: float = 120.0
    base_backoff_seconds: float = 0.25


@dataclass(frozen=True, slots=True)
class GroqRouteAttempt:
    model: str
    chain: GroqRouteChain
    attempt_index: int
    total_attempt_index: int
    fallback_reason: GroqLimitKind


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

    request_too_large_markers = (
        "request too large",
        "request_too_large",
        "too large for model",
        "payload too large",
        "maximum context length",
        "context length",
        "context_limit",
        "context window",
        "tokens requested",
        "reduce the length",
    )
    if any(marker in text for marker in request_too_large_markers):
        if "context" in text:
            return GroqLimitKind.CONTEXT_LIMIT
        return GroqLimitKind.REQUEST_TOO_LARGE

    if status_code == 429 or "ratelimit" in type_name:
        daily_markers = (
            "tokens per day",
            "requests per day",
            "daily",
            "tpd",
            "rpd",
            "quota exhausted",
            "daily quota",
        )
        if any(marker in text for marker in daily_markers):
            return GroqLimitKind.TPD

        if "tokens per minute" in text or "tpm" in text:
            return GroqLimitKind.TPM
        if "requests per minute" in text or "rpm" in text:
            return GroqLimitKind.RPM
        return GroqLimitKind.RATE_LIMIT

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


def is_transient_groq_limit(kind: GroqLimitKind) -> bool:
    return kind in {
        GroqLimitKind.TPM,
        GroqLimitKind.RPM,
        GroqLimitKind.RATE_LIMIT,
        GroqLimitKind.TEMPORARY_PROVIDER_ERROR,
    }


def is_daily_groq_quota(kind: GroqLimitKind) -> bool:
    return kind == GroqLimitKind.TPD


def is_groq_input_too_large(kind: GroqLimitKind) -> bool:
    return kind in {GroqLimitKind.REQUEST_TOO_LARGE, GroqLimitKind.CONTEXT_LIMIT}


def _dedupe_models(models: Iterable[str]) -> tuple[str, ...]:
    result: list[str] = []
    seen: set[str] = set()
    for model in models:
        if not model or model in seen or model in DISALLOWED_COMPILER_MODELS:
            continue
        result.append(model)
        seen.add(model)
    return tuple(result)


def _message_chars(kwargs: Mapping[str, object]) -> int:
    messages = kwargs.get("messages")
    if not isinstance(messages, Sequence) or isinstance(messages, (str, bytes)):
        return 0

    total = 0
    for message in messages:
        if not isinstance(message, Mapping):
            continue
        content = message.get("content")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, Sequence):
            total += sum(len(str(item)) for item in content)
    return total


def _is_large_request(kwargs: Mapping[str, object]) -> bool:
    max_tokens = kwargs.get("max_tokens")
    if isinstance(max_tokens, int) and max_tokens >= 2_000:
        return True
    return _message_chars(kwargs) >= 12_000


class GroqModelRouter:
    def __init__(self, policy: GroqFallbackPolicy | None = None) -> None:
        self._policy = policy or GroqFallbackPolicy()

    def select_chain(
        self,
        *,
        requested_model: str | None,
        kwargs: Mapping[str, object],
    ) -> tuple[GroqRouteChain, tuple[str, ...]]:
        if requested_model in DISALLOWED_COMPILER_MODELS:
            requested_model = None

        if _is_large_request(kwargs):
            chain_name = GroqRouteChain.LARGE_REQUEST
            chain = self._policy.large_request_chain
        elif requested_model in self._policy.cheap_small_chain:
            chain_name = GroqRouteChain.CHEAP_SMALL
            chain = self._policy.cheap_small_chain
        elif requested_model in self._policy.large_request_chain:
            chain_name = GroqRouteChain.LARGE_REQUEST
            chain = self._policy.large_request_chain
        else:
            chain_name = GroqRouteChain.PRIMARY
            chain = self._policy.primary_chain

        if requested_model:
            return chain_name, _dedupe_models((requested_model, *chain))
        return chain_name, _dedupe_models(chain)

    async def run_chat_completion(
        self,
        *,
        create_call: Callable[[dict[str, object]], Awaitable[ResultT]],
        kwargs: Mapping[str, object],
        operation_name: str,
    ) -> ResultT:
        requested_model = kwargs.get("model")
        requested_model_text = requested_model if isinstance(requested_model, str) else None
        chain_name, models = self.select_chain(
            requested_model=requested_model_text,
            kwargs=kwargs,
        )
        if not models:
            raise GroqFallbackExhaustedError(
                failure_type=GroqRouteFailureType.ALL_FALLBACKS_EXHAUSTED,
                message="No Groq fallback models are available for this call",
            )

        started_at = asyncio.get_running_loop().time()
        total_attempts = 0
        last_error: BaseException | None = None
        last_limit_kind = GroqLimitKind.NONE

        for model in models:
            model_attempts = 0
            fallback_reason = last_limit_kind
            while model_attempts < self._policy.max_attempts_per_model:
                elapsed = asyncio.get_running_loop().time() - started_at
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

                routed_kwargs = dict(kwargs)
                routed_kwargs["model"] = model
                model_attempts += 1
                total_attempts += 1
                attempt = GroqRouteAttempt(
                    model=model,
                    chain=chain_name,
                    attempt_index=model_attempts,
                    total_attempt_index=total_attempts,
                    fallback_reason=fallback_reason,
                )

                try:
                    self._log_attempt(operation_name=operation_name, attempt=attempt)
                    return await create_call(routed_kwargs)
                except Exception as exc:
                    last_error = exc
                    last_limit_kind = classify_groq_exception(exc)
                    fallback_reason = last_limit_kind
                    if last_limit_kind == GroqLimitKind.NONE:
                        raise

                    if is_groq_input_too_large(last_limit_kind):
                        logger.warning(
                            "Groq model rejected request size; trying next fallback model",
                            extra={
                                "operation": operation_name,
                                "model": model,
                                "limit_kind": last_limit_kind.value,
                                "chain": chain_name.value,
                            },
                        )
                        break

                    if is_daily_groq_quota(last_limit_kind):
                        logger.warning(
                            "Groq daily quota exhausted for route; trying next fallback model",
                            extra={
                                "operation": operation_name,
                                "model": model,
                                "limit_kind": last_limit_kind.value,
                                "chain": chain_name.value,
                            },
                        )
                        break

                    if is_transient_groq_limit(last_limit_kind):
                        await self._bounded_backoff(total_attempts=total_attempts)
                        if model_attempts < self._policy.max_attempts_per_model:
                            continue
                        logger.warning(
                            "Groq transient limit exhausted for model; trying fallback model",
                            extra={
                                "operation": operation_name,
                                "model": model,
                                "limit_kind": last_limit_kind.value,
                                "chain": chain_name.value,
                                "attempts_for_model": model_attempts,
                            },
                        )
                        break

                    raise

        raise self._exhausted_error(
            last_limit_kind=last_limit_kind,
            last_error=last_error,
            reason="all fallback models exhausted",
        )

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
