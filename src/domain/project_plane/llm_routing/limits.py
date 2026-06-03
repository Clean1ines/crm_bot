from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from .shared import require_non_negative_int, require_positive_int


class LlmLimitKind(StrEnum):
    RPM = "rpm"
    TPM = "tpm"
    RPD = "rpd"
    TPD = "tpd"
    CONTEXT_WINDOW = "context_window"
    MAX_OUTPUT_TOKENS = "max_output_tokens"
    CONCURRENCY = "concurrency"


@dataclass(frozen=True, slots=True)
class LlmModelLimits:
    requests_per_minute: int | None = None
    tokens_per_minute: int | None = None
    requests_per_day: int | None = None
    tokens_per_day: int | None = None
    context_window_tokens: int | None = None
    max_output_tokens: int | None = None
    max_concurrent_requests: int | None = None

    def __post_init__(self) -> None:
        self._validate_optional_positive(
            self.requests_per_minute,
            field_name="requests_per_minute",
        )
        self._validate_optional_positive(
            self.tokens_per_minute,
            field_name="tokens_per_minute",
        )
        self._validate_optional_positive(
            self.requests_per_day,
            field_name="requests_per_day",
        )
        self._validate_optional_positive(
            self.tokens_per_day,
            field_name="tokens_per_day",
        )
        self._validate_optional_positive(
            self.context_window_tokens,
            field_name="context_window_tokens",
        )
        self._validate_optional_positive(
            self.max_output_tokens,
            field_name="max_output_tokens",
        )
        self._validate_optional_positive(
            self.max_concurrent_requests,
            field_name="max_concurrent_requests",
        )

    def _validate_optional_positive(
        self, value: int | None, *, field_name: str
    ) -> None:
        if value is not None:
            require_positive_int(value, field_name=field_name)


@dataclass(frozen=True, slots=True)
class LlmTokenUsage:
    prompt_tokens: int
    completion_tokens: int

    def __post_init__(self) -> None:
        require_non_negative_int(self.prompt_tokens, field_name="prompt_tokens")
        require_non_negative_int(
            self.completion_tokens,
            field_name="completion_tokens",
        )

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens
