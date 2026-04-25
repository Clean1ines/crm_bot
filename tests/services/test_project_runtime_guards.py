from unittest.mock import AsyncMock

import pytest

from src.application.services.project_runtime_guards import ProjectRuntimeGuards
from src.application.ports.logger_port import NullLogger


@pytest.fixture
def redis():
    r = AsyncMock()
    r.incr = AsyncMock(return_value=1)
    r.expire = AsyncMock()
    r.scard = AsyncMock(return_value=0)
    r.sadd = AsyncMock()
    r.srem = AsyncMock()
    return r


def make_guards(redis):
    async def cache_factory():
        return redis

    return ProjectRuntimeGuards(cache_factory=cache_factory, logger=NullLogger())


@pytest.mark.asyncio
async def test_allow_request_uses_project_requests_per_minute(redis):
    guards = make_guards(redis)

    allowed = await guards.allow_request(
        "project-1",
        {"limits": {"requests_per_minute": 2}},
    )

    assert allowed is True
    redis.incr.assert_awaited_once()
    redis.expire.assert_awaited_once()


@pytest.mark.asyncio
async def test_allow_request_fails_open_when_redis_unavailable(redis):
    redis.incr.side_effect = RuntimeError("redis down")
    guards = make_guards(redis)

    allowed = await guards.allow_request(
        "project-1",
        {"limits": {"requests_per_minute": 2}},
    )

    assert allowed is True


@pytest.mark.asyncio
async def test_try_acquire_thread_slot_respects_max_concurrent_threads(redis):
    redis.exists.return_value = False
    redis.scard.return_value = 3
    guards = make_guards(redis)

    acquired = await guards.try_acquire_thread_slot(
        "project-1",
        "thread-1",
        {"limits": {"max_concurrent_threads": 2}},
    )

    assert acquired is False
    redis.sadd.assert_awaited_once()


@pytest.mark.asyncio
async def test_release_thread_slot_clears_runtime_slot(redis):
    guards = make_guards(redis)

    await guards.release_thread_slot("project-1", "thread-1")

    redis.srem.assert_awaited_once()
