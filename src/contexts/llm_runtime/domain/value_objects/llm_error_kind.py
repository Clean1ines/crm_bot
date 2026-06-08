from __future__ import annotations

from enum import StrEnum


class LlmErrorKind(StrEnum):
    REQUEST_TOO_LARGE = "request_too_large"
    OUTPUT_TOO_LARGE = "output_too_large"
    MINUTE_LIMIT = "minute_limit"
    DAILY_LIMIT = "daily_limit"
    INVALID_OUTPUT = "invalid_output"
    VALIDATION_FAILED = "validation_failed"
    EMPTY_OUTPUT = "empty_output"
    NETWORK_ERROR = "network_error"
    AUTH_ERROR = "auth_error"
    UNKNOWN = "unknown"
