from __future__ import annotations

import re
import time
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Final

_DURATION_PART_RE: Final[re.Pattern[str]] = re.compile(
    r"(?P<value>\d+(?:\.\d+)?)(?P<unit>ms|s|m|h|d)"
)


@dataclass(frozen=True, slots=True)
class GroqRateLimitHeaders:
    limit_requests: int | None = None
    remaining_requests: int | None = None
    reset_requests_seconds: float | None = None
    limit_tokens: int | None = None
    remaining_tokens: int | None = None
    reset_tokens_seconds: float | None = None
    retry_after_seconds: float | None = None

    @property
    def reset_requests_epoch(self) -> float | None:
        if self.reset_requests_seconds is None:
            return None
        return time.time() + self.reset_requests_seconds

    @property
    def reset_tokens_epoch(self) -> float | None:
        if self.reset_tokens_seconds is None:
            return None
        return time.time() + self.reset_tokens_seconds

    @property
    def blocking_reset_seconds(self) -> float | None:
        candidates: list[float] = []
        if self.remaining_requests == 0 and self.reset_requests_seconds is not None:
            candidates.append(self.reset_requests_seconds)
        if self.remaining_tokens == 0 and self.reset_tokens_seconds is not None:
            candidates.append(self.reset_tokens_seconds)
        if self.retry_after_seconds is not None:
            candidates.append(self.retry_after_seconds)
        return max(candidates) if candidates else None

    @property
    def has_values(self) -> bool:
        return any(
            value is not None
            for value in (
                self.limit_requests,
                self.remaining_requests,
                self.reset_requests_seconds,
                self.limit_tokens,
                self.remaining_tokens,
                self.reset_tokens_seconds,
                self.retry_after_seconds,
            )
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "limit_requests": self.limit_requests,
            "remaining_requests": self.remaining_requests,
            "reset_requests_seconds": self.reset_requests_seconds,
            "limit_tokens": self.limit_tokens,
            "remaining_tokens": self.remaining_tokens,
            "reset_tokens_seconds": self.reset_tokens_seconds,
            "retry_after_seconds": self.retry_after_seconds,
        }


def _int_or_none(value: object) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, str):
        text = value.strip()
        if text.isdigit():
            return int(text)
    return None


def _float_or_none(value: object) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        try:
            return float(text)
        except ValueError:
            return None
    return None


def parse_groq_reset_seconds(value: object) -> float | None:
    numeric = _float_or_none(value)
    if numeric is not None:
        if numeric > 1_000_000_000:
            return max(0.0, numeric - time.time())
        return max(0.0, numeric)

    if not isinstance(value, str):
        return None
    text = value.strip().lower()
    if not text:
        return None

    total = 0.0
    matched = False
    for match in _DURATION_PART_RE.finditer(text):
        matched = True
        amount = float(match.group("value"))
        unit = match.group("unit")
        if unit == "ms":
            total += amount / 1000.0
        elif unit == "s":
            total += amount
        elif unit == "m":
            total += amount * 60.0
        elif unit == "h":
            total += amount * 60.0 * 60.0
        elif unit == "d":
            total += amount * 24.0 * 60.0 * 60.0
    return total if matched else None


def _header_value(headers: Mapping[str, object], name: str) -> object | None:
    value = headers.get(name)
    if value is not None:
        return value
    lower_name = name.lower()
    for key, item in headers.items():
        if str(key).lower() == lower_name:
            return item
    return None


def _headers_mapping_from_source(source: object) -> Mapping[str, object] | None:
    if isinstance(source, Mapping):
        return source
    value = getattr(source, "headers", None)
    if isinstance(value, Mapping):
        return value
    for parent_attr in ("response", "http_response", "_response"):
        parent = getattr(source, parent_attr, None)
        if parent is None:
            continue
        value = getattr(parent, "headers", None)
        if isinstance(value, Mapping):
            return value
    return None


def groq_rate_limit_headers_from_source(source: object) -> GroqRateLimitHeaders:
    headers = _headers_mapping_from_source(source)
    if headers is None:
        return GroqRateLimitHeaders()

    return GroqRateLimitHeaders(
        limit_requests=_int_or_none(_header_value(headers, "x-ratelimit-limit-requests")),
        remaining_requests=_int_or_none(_header_value(headers, "x-ratelimit-remaining-requests")),
        reset_requests_seconds=parse_groq_reset_seconds(_header_value(headers, "x-ratelimit-reset-requests")),
        limit_tokens=_int_or_none(_header_value(headers, "x-ratelimit-limit-tokens")),
        remaining_tokens=_int_or_none(_header_value(headers, "x-ratelimit-remaining-tokens")),
        reset_tokens_seconds=parse_groq_reset_seconds(_header_value(headers, "x-ratelimit-reset-tokens")),
        retry_after_seconds=parse_groq_reset_seconds(_header_value(headers, "retry-after")),
    )
