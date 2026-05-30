from __future__ import annotations

import asyncio
import re
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Literal, Protocol, cast

from groq import AsyncGroq

from src.domain.project_plane.json_types import JsonObject, json_value_from_unknown
from src.infrastructure.llm.groq_keyring import configured_groq_api_keys

GroqRouteChainName = Literal["primary", "large_request", "cheap_small"]
GroqLimitKind = Literal[
    "request_too_large",
    "rate_limit_tpm_rpm",
    "daily_quota_exhausted",
    "provider_transient",
    "provider_non_retryable",
]

GROQ_PRIMARY_CHAIN: tuple[str, ...] = (
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "llama-3.3-70b-versatile",
    "qwen/qwen3-32b",
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "llama-3.1-8b-instant",
)
GROQ_LARGE_REQUEST_CHAIN: tuple[str, ...] = (
    "meta-llama/llama-4-scout-17b-16e-instruct",
    "llama-3.3-70b-versatile",
    "openai/gpt-oss-120b",
    "qwen/qwen3-32b",
)
GROQ_CHEAP_SMALL_CHAIN: tuple[str, ...] = (
    "llama-3.1-8b-instant",
    "qwen/qwen3-32b",
    "openai/gpt-oss-20b",
)
GROQ_FORBIDDEN_COMPILER_MODELS: frozenset[str] = frozenset(
    {
        "meta-llama/llama-prompt-guard-2-22m",
        "meta-llama/llama-prompt-guard-2-86m",
        "openai/gpt-oss-safeguard-20b",
        "canopylabs/orpheus-v1-english",
        "groq/compound",
        "groq/compound-mini",
    }
)


class GroqChatCompletions(Protocol):
    async def create(self, *args: object, **kwargs: object) -> object: ...


class GroqChatNamespace(Protocol):
    completions: GroqChatCompletions


class GroqClient(Protocol):
    chat: GroqChatNamespace


@dataclass(frozen=True, slots=True)
class GroqFallbackPolicy:
    primary_chain: tuple[str, ...] = GROQ_PRIMARY_CHAIN
    large_request_chain: tuple[str, ...] = GROQ_LARGE_REQUEST_CHAIN
    cheap_small_chain: tuple[str, ...] = GROQ_CHEAP_SMALL_CHAIN
    max_attempts_per_call: int = 8
    max_attempts_per_model: int = 2
    max_total_llm_calls_per_document: int = 180
    max_elapsed_seconds_per_document: float = 900.0
    retry_base_seconds: float = 0.25
    retry_max_seconds: float = 2.0


@dataclass(frozen=True, slots=True)
class GroqRouteAttempt:
    attempt_index: int
    chain_name: GroqRouteChainName
    model: str
    key_alias: str
    limit_kind: GroqLimitKind | None = None
    error_type: str = ""
    fallback_reason: str = ""

    def to_json(self) -> JsonObject:
        return {
            "attempt_index": self.attempt_index,
            "chain_name": self.chain_name,
            "model": self.model,
            "key_alias": self.key_alias,
            "limit_kind": self.limit_kind or "",
            "error_type": self.error_type,
            "fallback_reason": self.fallback_reason,
        }


@dataclass(frozen=True, slots=True)
class GroqRouteResult:
    model: str
    key_alias: str
    content: str
    chain_name: GroqRouteChainName
    attempt_count: int
    fallback_reason: str
    attempts: tuple[GroqRouteAttempt, ...]
    tokens_input: int = 0
    tokens_output: int = 0
    tokens_total: int = 0

    def to_metrics(self) -> JsonObject:
        return {
            "model": self.model,
            "key_alias": self.key_alias,
            "chain_name": self.chain_name,
            "attempt_count": self.attempt_count,
            "fallback_reason": self.fallback_reason,
            "tokens_input": self.tokens_input,
            "tokens_output": self.tokens_output,
            "tokens_total": self.tokens_total,
            "attempts": [item.to_json() for item in self.attempts],
        }


@dataclass(frozen=True, slots=True)
class GroqRouterError(Exception):
    message: str
    error_type: str
    retry_after_seconds: int | None = None
    attempts: tuple[GroqRouteAttempt, ...] = field(default_factory=tuple)

    def __str__(self) -> str:
        return self.message

    def to_metrics(self) -> JsonObject:
        return {
            "error_type": self.error_type,
            "retry_after_seconds": self.retry_after_seconds or 0,
            "attempts": [item.to_json() for item in self.attempts],
        }


class GroqInputTooLargeError(GroqRouterError):
    pass


class GroqQuotaExhaustedError(GroqRouterError):
    pass


class GroqAllFallbacksExhaustedError(GroqRouterError):
    pass


def classify_groq_limit_error(exc: BaseException) -> GroqLimitKind:
    status_code = _status_code(exc)
    text = _error_text(exc)
    type_name = type(exc).__name__.lower()
    if status_code == 413 or _has(
        text,
        (
            "request too large",
            "context limit",
            "context_length_exceeded",
            "maximum context",
            "max context",
            "too many tokens",
            "input too large",
        ),
    ):
        return "request_too_large"
    if _has(
        text,
        (
            "tokens per day",
            "requests per day",
            "tpd",
            "rpd",
            "daily quota",
            "quota exhausted",
            "daily limit",
        ),
    ):
        return "daily_quota_exhausted"
    if status_code == 429 or "ratelimit" in type_name:
        return "rate_limit_tpm_rpm"
    if status_code in {408, 409, 425, 500, 502, 503, 504}:
        return "provider_transient"
    return "provider_non_retryable"


def retry_after_seconds_from_error(exc: BaseException) -> int | None:
    match = re.search(
        r"try again in\s+(?P<seconds>[0-9]+(?:\.[0-9]+)?)s", _error_text(exc)
    )
    if match is None:
        return None
    return max(1, int(float(match.group("seconds")) + 0.999))


class GroqModelRouter:
    def __init__(
        self,
        *,
        policy: GroqFallbackPolicy | None = None,
        client: GroqClient | None = None,
        api_keys: Sequence[str] | None = None,
    ) -> None:
        self._policy = policy or GroqFallbackPolicy()
        self._client = client
        self._api_keys = tuple(api_keys) if api_keys is not None else None

    @property
    def policy(self) -> GroqFallbackPolicy:
        return self._policy

    async def request_json(
        self,
        *,
        system_message: str,
        prompt: str,
        max_tokens: int,
        chain_name: GroqRouteChainName = "primary",
    ) -> GroqRouteResult:
        active_chain, fallback_reason = self._initial_chain(
            chain_name=chain_name,
        )
        attempts: list[GroqRouteAttempt] = []
        last_error: BaseException | None = None
        only_daily_quota = True
        request_too_large = False
        visited_large_chain = active_chain == "large_request"
        keys = self._keys()

        while True:
            for model in self._chain(active_chain):
                if model in GROQ_FORBIDDEN_COMPILER_MODELS:
                    continue
                model_attempt_count = 0
                for key_index, key in enumerate(keys):
                    if model_attempt_count >= self._policy.max_attempts_per_model:
                        break
                    if len(attempts) >= self._policy.max_attempts_per_call:
                        raise self._final_error(
                            attempts, last_error, only_daily_quota, request_too_large
                        )
                    model_attempt_count += 1
                    attempt_index = len(attempts) + 1
                    key_alias = (
                        "injected"
                        if self._client is not None
                        else f"groq_key_{key_index + 1}"
                    )
                    try:
                        response = await self._client_for_key(
                            key
                        ).chat.completions.create(
                            model=model,
                            messages=[
                                {"role": "system", "content": system_message},
                                {"role": "user", "content": prompt},
                            ],
                            temperature=0,
                            max_tokens=max_tokens,
                            response_format={"type": "json_object"},
                        )
                        attempts.append(
                            GroqRouteAttempt(
                                attempt_index,
                                active_chain,
                                model,
                                key_alias,
                                fallback_reason=fallback_reason,
                            )
                        )
                        return GroqRouteResult(
                            model=model,
                            key_alias=key_alias,
                            content=_response_content(response),
                            chain_name=active_chain,
                            attempt_count=len(attempts),
                            fallback_reason=fallback_reason,
                            attempts=tuple(attempts),
                            tokens_input=_usage_count(response, "prompt_tokens"),
                            tokens_output=_usage_count(response, "completion_tokens"),
                            tokens_total=_usage_count(response, "total_tokens"),
                        )
                    except Exception as exc:
                        last_error = exc
                        limit_kind = classify_groq_limit_error(exc)
                        only_daily_quota = (
                            only_daily_quota and limit_kind == "daily_quota_exhausted"
                        )
                        request_too_large = (
                            request_too_large or limit_kind == "request_too_large"
                        )
                        attempts.append(
                            GroqRouteAttempt(
                                attempt_index,
                                active_chain,
                                model,
                                key_alias,
                                limit_kind,
                                type(exc).__name__,
                                fallback_reason,
                            )
                        )
                        if limit_kind == "request_too_large":
                            break
                        if limit_kind == "daily_quota_exhausted":
                            continue
                        if limit_kind in {"rate_limit_tpm_rpm", "provider_transient"}:
                            await self._backoff(attempt_index)
                            continue
                        break
            if request_too_large and not visited_large_chain:
                active_chain = "large_request"
                fallback_reason = "request_too_large"
                visited_large_chain = True
                request_too_large = False
                continue
            raise self._final_error(
                attempts, last_error, only_daily_quota, request_too_large
            )

    def _initial_chain(
        self, *, chain_name: GroqRouteChainName
    ) -> tuple[GroqRouteChainName, str]:
        # Provider response is the source of truth. Do not estimate output
        # tokens or jump to large models before a provider failure.
        return chain_name, ""

    def _chain(self, chain_name: GroqRouteChainName) -> tuple[str, ...]:
        if chain_name == "large_request":
            return self._policy.large_request_chain
        if chain_name == "cheap_small":
            return self._policy.cheap_small_chain
        return self._policy.primary_chain

    def _keys(self) -> tuple[str, ...]:
        if self._client is not None:
            return ("injected",)
        keys = (
            self._api_keys if self._api_keys is not None else configured_groq_api_keys()
        )
        if not keys:
            raise GroqAllFallbacksExhaustedError(
                "No Groq API keys configured", "groq_keys_not_configured"
            )
        return keys

    def _client_for_key(self, key: str) -> GroqClient:
        if self._client is not None:
            return self._client
        return cast(GroqClient, AsyncGroq(api_key=key))

    async def _backoff(self, attempt_index: int) -> None:
        delay = min(
            self._policy.retry_max_seconds,
            self._policy.retry_base_seconds * max(1, attempt_index),
        )
        if delay > 0:
            await asyncio.sleep(delay)

    def _final_error(
        self,
        attempts: Sequence[GroqRouteAttempt],
        last_error: BaseException | None,
        only_daily_quota: bool,
        request_too_large: bool,
    ) -> GroqRouterError:
        frozen_attempts = tuple(attempts)
        retry_after = (
            retry_after_seconds_from_error(last_error)
            if last_error is not None
            else None
        )
        if request_too_large:
            return GroqInputTooLargeError(
                "All large-request Groq compiler models rejected the input size",
                "input_too_large",
                retry_after,
                frozen_attempts,
            )
        if frozen_attempts and only_daily_quota:
            return GroqQuotaExhaustedError(
                "All Groq compiler routes are exhausted for the current quota window",
                "groq_quota_exhausted",
                retry_after,
                frozen_attempts,
            )
        return GroqAllFallbacksExhaustedError(
            "All Groq compiler fallback routes were exhausted",
            "all_fallbacks_exhausted",
            retry_after,
            frozen_attempts,
        )


def route_error_metrics(exc: GroqRouterError) -> JsonObject:
    return {
        **exc.to_metrics(),
        "partial_surfaces_available": json_value_from_unknown(True),
        "recoverable_quota_pause": json_value_from_unknown(
            isinstance(exc, GroqQuotaExhaustedError)
        ),
    }


def _status_code(exc: BaseException) -> int | None:
    status = getattr(exc, "status_code", None)
    if isinstance(status, int):
        return status
    response = getattr(exc, "response", None)
    response_status = getattr(response, "status_code", None)
    return response_status if isinstance(response_status, int) else None


def _error_text(exc: BaseException) -> str:
    parts = [str(exc)]
    body = getattr(exc, "body", None)
    if body is not None:
        parts.append(str(body))
    return " ".join(parts).lower()


def _has(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _response_content(response: object) -> str:
    choices = getattr(response, "choices", ())
    if not isinstance(choices, Sequence) or not choices:
        return ""
    message = getattr(choices[0], "message", None)
    content = getattr(message, "content", "")
    return content if isinstance(content, str) else ""


def _usage_count(response: object, name: str) -> int:
    usage = getattr(response, "usage", None)
    value = getattr(usage, name, 0)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return 0
