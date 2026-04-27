"""Retry policy for background queue jobs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping
import random

MAX_RETRIES = 3


def _coerce_int(value: object, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return int(stripped)
        except ValueError:
            return default
    return default


INITIAL_BACKOFF_SECONDS = 1
MAX_BACKOFF_SECONDS = 60


@dataclass(frozen=True)
class RetryDecision:
    should_retry: bool
    exhausted: bool
    backoff_seconds: float
    error: str


def calculate_backoff(attempt: int) -> float:
    """Calculate exponential backoff with small jitter."""
    safe_attempt = max(int(attempt or 0), 0)
    delay = min(INITIAL_BACKOFF_SECONDS * (2**safe_attempt), MAX_BACKOFF_SECONDS)
    jitter = random.uniform(0, delay * 0.1)
    return delay + jitter


def build_retry_decision(job: Mapping[str, object], error: str) -> RetryDecision:
    """
    Decide whether a transient job failure should be retried.

    QueueRepository.fail_job(increment_attempt=True) is responsible for
    incrementing attempts and returning the job to pending or failed.
    """
    attempts = _coerce_int(job.get("attempts"), 0)
    max_attempts = _coerce_int(job.get("max_attempts"), MAX_RETRIES)

    exhausted = attempts + 1 >= max_attempts
    return RetryDecision(
        should_retry=not exhausted,
        exhausted=exhausted,
        backoff_seconds=0.0 if exhausted else calculate_backoff(attempts),
        error=error,
    )
