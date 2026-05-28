from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from hashlib import sha256
from typing import Final

from src.infrastructure.config.settings import settings
from src.infrastructure.llm.groq_router import (
    GroqLimitKind,
    is_daily_groq_quota,
    is_minute_groq_limit,
)
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.redis.client import get_redis_client

logger = get_logger(__name__)

_PROVIDER: Final[str] = "groq"
_KEY_PREFIX: Final[str] = "llm_quota_state"
_DEFAULT_DAILY_COOLDOWN_SECONDS: Final[float] = 24 * 60 * 60
_DEFAULT_MINUTE_COOLDOWN_SECONDS: Final[float] = 60.0
_MAX_PREFLIGHT_SLEEP_SECONDS: Final[float] = 65.0
_STATE_TTL_SECONDS: Final[int] = 3 * 24 * 60 * 60


class GroqRouteQuotaBlockedError(RuntimeError):
    """Raised when a Groq key/model route is known to be cooling down."""

    status_code = 429

    def __init__(self, message: str, *, retry_after: float) -> None:
        super().__init__(message)
        self.retry_after = retry_after


@dataclass(frozen=True, slots=True)
class GroqRouteQuotaIdentity:
    provider: str
    key_hash: str
    key_index: int
    key_count: int
    model: str

    @property
    def redis_key(self) -> str:
        return f"{_KEY_PREFIX}:{self.provider}:{self.key_hash}:{self.model}"


@dataclass(frozen=True, slots=True)
class GroqRouteQuotaState:
    cooldown_until_monotonic: float | None
    cooldown_until_epoch: float | None
    limit_kind: str
    failure_count: int
    last_error: str
    updated_at_epoch: float

    @property
    def is_blocking_now(self) -> bool:
        if self.cooldown_until_monotonic is not None:
            return self.cooldown_until_monotonic > time.monotonic()
        if self.cooldown_until_epoch is not None:
            return self.cooldown_until_epoch > time.time()
        return False

    @property
    def remaining_seconds(self) -> float:
        if self.cooldown_until_monotonic is not None:
            return max(0.0, self.cooldown_until_monotonic - time.monotonic())
        if self.cooldown_until_epoch is not None:
            return max(0.0, self.cooldown_until_epoch - time.time())
        return 0.0


@dataclass(slots=True)
class _InMemoryQuotaStateStore:
    states: dict[str, GroqRouteQuotaState]
    lock: asyncio.Lock


_MEMORY_STORE = _InMemoryQuotaStateStore(states={}, lock=asyncio.Lock())


def _key_hash(raw_key: str) -> str:
    return sha256(raw_key.encode("utf-8")).hexdigest()[:16]


def groq_route_quota_identity(
    *,
    api_key: str,
    key_index: int,
    key_count: int,
    model: str,
) -> GroqRouteQuotaIdentity:
    return GroqRouteQuotaIdentity(
        provider=_PROVIDER,
        key_hash=_key_hash(api_key),
        key_index=key_index,
        key_count=key_count,
        model=model,
    )


def _state_from_payload(payload: str) -> GroqRouteQuotaState | None:
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None

    cooldown_until_epoch = data.get("cooldown_until_epoch")
    if isinstance(cooldown_until_epoch, bool) or not isinstance(
        cooldown_until_epoch, int | float
    ):
        cooldown_until_epoch = None

    failure_count = data.get("failure_count")
    if isinstance(failure_count, bool) or not isinstance(failure_count, int):
        failure_count = 0

    limit_kind = data.get("limit_kind")
    last_error = data.get("last_error")
    updated_at_epoch = data.get("updated_at_epoch")
    if isinstance(updated_at_epoch, bool) or not isinstance(updated_at_epoch, int | float):
        updated_at_epoch = time.time()

    return GroqRouteQuotaState(
        cooldown_until_monotonic=None,
        cooldown_until_epoch=float(cooldown_until_epoch)
        if cooldown_until_epoch is not None
        else None,
        limit_kind=str(limit_kind or GroqLimitKind.NONE.value),
        failure_count=max(0, failure_count),
        last_error=str(last_error or ""),
        updated_at_epoch=float(updated_at_epoch),
    )


def _state_to_payload(state: GroqRouteQuotaState) -> str:
    cooldown_until_epoch = state.cooldown_until_epoch
    if cooldown_until_epoch is None and state.cooldown_until_monotonic is not None:
        remaining = max(0.0, state.cooldown_until_monotonic - time.monotonic())
        cooldown_until_epoch = time.time() + remaining
    return json.dumps(
        {
            "cooldown_until_epoch": cooldown_until_epoch,
            "limit_kind": state.limit_kind,
            "failure_count": state.failure_count,
            "last_error": state.last_error,
            "updated_at_epoch": state.updated_at_epoch,
        },
        ensure_ascii=False,
    )


async def _redis_get(identity: GroqRouteQuotaIdentity) -> GroqRouteQuotaState | None:
    if not settings.REDIS_URL:
        return None
    try:
        client = await get_redis_client()
        payload = await client.get(identity.redis_key)
    except Exception as exc:
        logger.warning(
            "Groq quota Redis read failed; using process-local quota state only",
            extra={"error_type": type(exc).__name__, "error": str(exc)[:240]},
        )
        return None
    if not isinstance(payload, str):
        return None
    return _state_from_payload(payload)


async def _redis_set(
    identity: GroqRouteQuotaIdentity,
    state: GroqRouteQuotaState,
) -> None:
    if not settings.REDIS_URL:
        return
    try:
        client = await get_redis_client()
        await client.set(identity.redis_key, _state_to_payload(state), ex=_STATE_TTL_SECONDS)
    except Exception as exc:
        logger.warning(
            "Groq quota Redis write failed; using process-local quota state only",
            extra={"error_type": type(exc).__name__, "error": str(exc)[:240]},
        )


async def _redis_delete(identity: GroqRouteQuotaIdentity) -> None:
    if not settings.REDIS_URL:
        return
    try:
        client = await get_redis_client()
        await client.delete(identity.redis_key)
    except Exception as exc:
        logger.warning(
            "Groq quota Redis delete failed",
            extra={"error_type": type(exc).__name__, "error": str(exc)[:240]},
        )


async def _memory_get(identity: GroqRouteQuotaIdentity) -> GroqRouteQuotaState | None:
    async with _MEMORY_STORE.lock:
        state = _MEMORY_STORE.states.get(identity.redis_key)
        if state is None:
            return None
        if not state.is_blocking_now:
            _MEMORY_STORE.states.pop(identity.redis_key, None)
            return None
        return state


async def _memory_set(
    identity: GroqRouteQuotaIdentity,
    state: GroqRouteQuotaState,
) -> None:
    async with _MEMORY_STORE.lock:
        _MEMORY_STORE.states[identity.redis_key] = state


async def _memory_delete(identity: GroqRouteQuotaIdentity) -> None:
    async with _MEMORY_STORE.lock:
        _MEMORY_STORE.states.pop(identity.redis_key, None)


async def get_groq_route_quota_state(
    identity: GroqRouteQuotaIdentity,
) -> GroqRouteQuotaState | None:
    redis_state = await _redis_get(identity)
    if redis_state is not None and redis_state.is_blocking_now:
        return redis_state
    return await _memory_get(identity)


async def wait_or_block_groq_route(identity: GroqRouteQuotaIdentity) -> None:
    state = await get_groq_route_quota_state(identity)
    if state is None:
        return

    remaining = state.remaining_seconds
    if remaining <= 0:
        await clear_groq_route_quota_state(identity)
        return

    if remaining <= _MAX_PREFLIGHT_SLEEP_SECONDS:
        logger.info(
            "Waiting for Groq route cooldown before request",
            extra={
                "key_index": identity.key_index + 1,
                "key_count": identity.key_count,
                "model": identity.model,
                "limit_kind": state.limit_kind,
                "sleep_seconds": round(remaining, 3),
            },
        )
        await asyncio.sleep(remaining)
        return

    raise GroqRouteQuotaBlockedError(
        "groq_quota_exhausted: route is cooling down for "
        f"{round(remaining, 1)}s; model={identity.model}; "
        f"key_slot={identity.key_index + 1}/{identity.key_count}; "
        f"limit_kind={state.limit_kind}; try again in {round(remaining, 1)}s",
        retry_after=remaining,
    )


async def clear_groq_route_quota_state(identity: GroqRouteQuotaIdentity) -> None:
    await _memory_delete(identity)
    await _redis_delete(identity)


def _cooldown_seconds_for_limit(
    *,
    limit_kind: GroqLimitKind,
    retry_after_seconds: float | None,
) -> float | None:
    if is_daily_groq_quota(limit_kind):
        return max(retry_after_seconds or 0.0, _DEFAULT_DAILY_COOLDOWN_SECONDS)
    if is_minute_groq_limit(limit_kind):
        return max(retry_after_seconds or 0.0, _DEFAULT_MINUTE_COOLDOWN_SECONDS)
    if limit_kind == GroqLimitKind.TEMPORARY_PROVIDER_ERROR:
        return max(retry_after_seconds or 0.0, _DEFAULT_MINUTE_COOLDOWN_SECONDS)
    return None


async def record_groq_route_failure(
    *,
    identity: GroqRouteQuotaIdentity,
    limit_kind: GroqLimitKind,
    retry_after_seconds: float | None,
    error: str,
) -> None:
    cooldown_seconds = _cooldown_seconds_for_limit(
        limit_kind=limit_kind,
        retry_after_seconds=retry_after_seconds,
    )
    if cooldown_seconds is None:
        return

    previous = await get_groq_route_quota_state(identity)
    failure_count = 1 if previous is None else previous.failure_count + 1
    state = GroqRouteQuotaState(
        cooldown_until_monotonic=time.monotonic() + cooldown_seconds,
        cooldown_until_epoch=time.time() + cooldown_seconds,
        limit_kind=limit_kind.value,
        failure_count=failure_count,
        last_error=error[:300],
        updated_at_epoch=time.time(),
    )
    await _memory_set(identity, state)
    await _redis_set(identity, state)
    logger.warning(
        "Groq route quota state updated",
        extra={
            "key_index": identity.key_index + 1,
            "key_count": identity.key_count,
            "model": identity.model,
            "limit_kind": limit_kind.value,
            "cooldown_seconds": round(cooldown_seconds, 3),
            "failure_count": failure_count,
        },
    )


async def record_groq_route_success(identity: GroqRouteQuotaIdentity) -> None:
    await clear_groq_route_quota_state(identity)
