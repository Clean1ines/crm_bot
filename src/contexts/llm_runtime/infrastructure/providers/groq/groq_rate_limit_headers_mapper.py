from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Mapping

from src.contexts.llm_runtime.application.policies.llm_quota_availability_policy import (
    LlmQuotaSnapshot,
)


@dataclass(frozen=True, slots=True)
class GroqRateLimitHeadersMapper:
    """Map Groq HTTP rate-limit headers to provider-neutral quota snapshot.

    Groq rate-limit headers use:
    - x-ratelimit-remaining-requests for remaining requests per day;
    - x-ratelimit-remaining-tokens for remaining tokens per minute;
    - x-ratelimit-reset-requests for request/day reset duration;
    - x-ratelimit-reset-tokens for token/minute reset duration;
    - retry-after when a 429 limit was hit.
    """

    def map_headers(
        self,
        *,
        headers: Mapping[str, str],
        observed_at: datetime,
    ) -> LlmQuotaSnapshot:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")

        normalized = {key.lower(): value for key, value in headers.items()}

        retry_after = self._parse_duration_seconds(normalized.get("retry-after"))
        reset_tokens = self._parse_duration_seconds(
            normalized.get("x-ratelimit-reset-tokens")
        )
        reset_requests = self._parse_duration_seconds(
            normalized.get("x-ratelimit-reset-requests")
        )
        minute_reset_at = self._absolute_reset_at(
            observed_at=observed_at,
            duration_seconds=reset_tokens,
        )
        daily_reset_at = self._absolute_reset_at(
            observed_at=observed_at,
            duration_seconds=reset_requests,
        )

        unavailable_until = self._nearest_future_time(
            observed_at=observed_at,
            durations_seconds=(
                retry_after,
                reset_tokens,
                reset_requests,
            ),
        )

        return LlmQuotaSnapshot(
            remaining_requests_day=self._parse_int(
                normalized.get("x-ratelimit-remaining-requests"),
            ),
            remaining_tokens_minute=self._parse_int(
                normalized.get("x-ratelimit-remaining-tokens"),
            ),
            minute_reset_at=minute_reset_at,
            daily_reset_at=daily_reset_at,
            unavailable_until=unavailable_until,
        )

    def _parse_int(self, value: str | None) -> int | None:
        if value is None or not value.strip():
            return None

        try:
            parsed = int(value.strip())
        except ValueError:
            return None

        if parsed < 0:
            return None

        return parsed

    def _parse_duration_seconds(self, value: str | None) -> float | None:
        if value is None or not value.strip():
            return None

        text = value.strip().lower()

        try:
            return max(float(text), 0.0)
        except ValueError:
            pass

        parts = re.findall(r"(\d+(?:\.\d+)?)([hms])", text)
        if not parts:
            return None

        reconstructed = "".join(f"{value}{unit}" for value, unit in parts)
        if reconstructed != text:
            return None

        total = 0.0
        for value_raw, unit in parts:
            value_num = float(value_raw)
            if unit == "h":
                total += value_num * 3600.0
            elif unit == "m":
                total += value_num * 60.0
            else:
                total += value_num

        return total if total > 0 else None

    def _absolute_reset_at(
        self,
        *,
        observed_at: datetime,
        duration_seconds: float | None,
    ) -> datetime | None:
        if duration_seconds is None:
            return None
        return observed_at + timedelta(seconds=duration_seconds)

    def _nearest_future_time(
        self,
        *,
        observed_at: datetime,
        durations_seconds: tuple[float | None, ...],
    ) -> datetime | None:
        candidates = tuple(
            observed_at + timedelta(seconds=duration)
            for duration in durations_seconds
            if duration is not None
        )

        if not candidates:
            return None

        return min(candidates)
