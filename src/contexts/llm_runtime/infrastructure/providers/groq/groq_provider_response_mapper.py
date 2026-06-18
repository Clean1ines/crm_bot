from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from src.contexts.llm_runtime.application.policies.llm_quota_availability_policy import (
    LlmQuotaSnapshot,
)
from src.contexts.llm_runtime.application.ports.llm_provider_port import (
    LlmProviderFailure,
    LlmProviderResult,
    LlmProviderSuccess,
)
from src.contexts.llm_runtime.domain.value_objects.llm_error_kind import LlmErrorKind
from src.contexts.llm_runtime.domain.value_objects.token_usage import TokenUsage
from src.contexts.llm_runtime.infrastructure.providers.groq.groq_rate_limit_headers_mapper import (
    GroqRateLimitHeadersMapper,
)


JsonObject = Mapping[str, object]


@dataclass(frozen=True, slots=True)
class GroqProviderHttpResponse:
    status_code: int
    headers: Mapping[str, str]
    body: JsonObject

    def __post_init__(self) -> None:
        if self.status_code < 100:
            raise ValueError("status_code must be a valid HTTP status code")


@dataclass(frozen=True, slots=True)
class GroqProviderMappedResponse:
    provider_result: LlmProviderResult
    quota_snapshot: LlmQuotaSnapshot


class GroqProviderResponseMapper:
    """Map Groq HTTP response data to provider-neutral LLM Runtime results.

    This mapper does not decide retry/fallback behavior. It only classifies the
    provider response and extracts quota/usage/content signals.
    """

    def __init__(
        self,
        *,
        headers_mapper: GroqRateLimitHeadersMapper | None = None,
    ) -> None:
        self._headers_mapper = headers_mapper or GroqRateLimitHeadersMapper()

    def map_response(
        self,
        *,
        response: GroqProviderHttpResponse,
        observed_at: datetime,
    ) -> GroqProviderMappedResponse:
        quota_snapshot = self._headers_mapper.map_headers(
            headers=response.headers,
            observed_at=observed_at,
        )

        if 200 <= response.status_code < 300:
            return GroqProviderMappedResponse(
                provider_result=LlmProviderSuccess(
                    raw_text=self._extract_chat_content(response.body),
                    usage=self._extract_usage(response.body),
                ),
                quota_snapshot=quota_snapshot,
            )

        return GroqProviderMappedResponse(
            provider_result=LlmProviderFailure(
                error_kind=self._classify_error(
                    status_code=response.status_code,
                    body=response.body,
                ),
                wait_until=quota_snapshot.unavailable_until,
            ),
            quota_snapshot=quota_snapshot,
        )

    def _extract_chat_content(self, body: JsonObject) -> str:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices:
            return ""

        first_choice = choices[0]
        if not isinstance(first_choice, Mapping):
            return ""

        message = first_choice.get("message")
        if not isinstance(message, Mapping):
            return ""

        content = message.get("content")
        if not isinstance(content, str):
            return ""

        return content

    def _extract_usage(self, body: JsonObject) -> TokenUsage | None:
        usage = body.get("usage")
        if not isinstance(usage, Mapping):
            return None

        prompt_tokens = usage.get("prompt_tokens")
        if not isinstance(prompt_tokens, int):
            prompt_tokens = usage.get("input_tokens")

        completion_tokens = usage.get("completion_tokens")
        if not isinstance(completion_tokens, int):
            completion_tokens = usage.get("output_tokens")

        if not isinstance(prompt_tokens, int) or not isinstance(completion_tokens, int):
            return None

        if prompt_tokens < 0 or completion_tokens < 0:
            return None

        return TokenUsage(
            input_tokens=prompt_tokens,
            output_tokens=completion_tokens,
        )

    def _classify_error(
        self,
        *,
        status_code: int,
        body: JsonObject,
    ) -> LlmErrorKind:
        error_text = self._error_text(body)

        if status_code == 401 or status_code == 403:
            return LlmErrorKind.AUTH_ERROR

        if status_code == 429:
            if (
                "daily" in error_text
                or "per day" in error_text
                or "rpd" in error_text
                or "tpd" in error_text
            ):
                return LlmErrorKind.DAILY_LIMIT
            return LlmErrorKind.MINUTE_LIMIT

        if status_code == 413:
            return LlmErrorKind.REQUEST_TOO_LARGE

        if status_code == 400:
            if (
                "context" in error_text
                or "too large" in error_text
                or "maximum context" in error_text
            ):
                return LlmErrorKind.REQUEST_TOO_LARGE
            if (
                "max_completion" in error_text
                or "completion tokens" in error_text
                or "output" in error_text
            ):
                return LlmErrorKind.OUTPUT_TOO_LARGE
            return LlmErrorKind.INVALID_OUTPUT

        if 500 <= status_code < 600:
            return LlmErrorKind.NETWORK_ERROR

        return LlmErrorKind.UNKNOWN

    def _error_text(self, body: JsonObject) -> str:
        error = body.get("error")

        if isinstance(error, Mapping):
            message = error.get("message")
            error_type = error.get("type")
            code = error.get("code")
            parts = tuple(
                part for part in (message, error_type, code) if isinstance(part, str)
            )
            return " ".join(parts).lower()

        if isinstance(error, str):
            return error.lower()

        message = body.get("message")
        if isinstance(message, str):
            return message.lower()

        return ""
