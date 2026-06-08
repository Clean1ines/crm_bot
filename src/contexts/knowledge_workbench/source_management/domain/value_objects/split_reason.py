from __future__ import annotations

from enum import StrEnum


class SplitReason(StrEnum):
    INITIAL_PARSE = "initial_parse"
    PROMPT_FIT = "prompt_fit"
    REQUEST_TOO_LARGE = "request_too_large"
    OUTPUT_TOO_LARGE = "output_too_large"
    USER_FORCED = "user_forced"
