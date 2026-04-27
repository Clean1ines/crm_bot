"""
Runtime guards driven by explicit project configuration.
"""

import time

from src.application.ports.cache_port import (
    CacheFactoryPort,
    NullCache,
    RuntimeCachePort,
)
from src.application.ports.logger_port import LoggerPort, NullLogger
from src.domain.runtime.project_runtime_profile import ProjectRuntimeProfile
from src.domain.runtime.state_contracts import ProjectRuntimeConfigurationState


ProjectConfigurationPayload = ProjectRuntimeConfigurationState


class ProjectRuntimeGuards:
    REDIS_PREFIX = "project_runtime:"

    def __init__(
        self,
        *,
        cache_factory: CacheFactoryPort | None = None,
        logger: LoggerPort | None = None,
    ) -> None:
        self.cache_factory = cache_factory
        self.logger = logger or NullLogger()

    async def _cache(self) -> RuntimeCachePort:
        if self.cache_factory is None:
            return NullCache()
        return await self.cache_factory()

    async def allow_request(
        self, project_id: str, project_configuration: ProjectConfigurationPayload | None
    ) -> bool:
        profile = ProjectRuntimeProfile.from_configuration(project_configuration)
        if profile.requests_per_minute is None:
            return True

        key = f"{self.REDIS_PREFIX}{project_id}:requests:{int(time.time() // 60)}"

        try:
            cache = await self._cache()
            current = await cache.incr(key)
            if int(current) == 1:
                await cache.expire(key, 70)
            return int(current) <= profile.requests_per_minute
        except Exception as exc:
            self.logger.warning(
                "Project request rate guard failed closed",
                extra={
                    "project_id": project_id,
                    "error_type": type(exc).__name__,
                },
            )
            return False

    async def try_acquire_thread_slot(
        self,
        project_id: str,
        thread_id: str,
        project_configuration: ProjectConfigurationPayload | None,
    ) -> bool:
        profile = ProjectRuntimeProfile.from_configuration(project_configuration)
        if profile.max_concurrent_threads is None:
            return True

        active_threads_key = f"{self.REDIS_PREFIX}{project_id}:active_threads"
        slot_key = f"{self.REDIS_PREFIX}{project_id}:thread:{thread_id}"

        try:
            cache = await self._cache()
            if await cache.exists(slot_key):
                await cache.expire(slot_key, 70)
                await cache.expire(active_threads_key, 70)
                return True

            await cache.sadd(active_threads_key, thread_id)
            await cache.set(slot_key, "1", ex=70)
            active_count = await cache.scard(active_threads_key)
            await cache.expire(active_threads_key, 70)

            if int(active_count) > profile.max_concurrent_threads:
                await cache.srem(active_threads_key, thread_id)
                await cache.delete(slot_key)
                return False

            return True
        except Exception as exc:
            self.logger.warning(
                "Project thread concurrency guard failed closed",
                extra={
                    "project_id": project_id,
                    "thread_id": thread_id,
                    "error_type": type(exc).__name__,
                },
            )
            return False

    async def release_thread_slot(self, project_id: str, thread_id: str) -> None:
        active_threads_key = f"{self.REDIS_PREFIX}{project_id}:active_threads"
        slot_key = f"{self.REDIS_PREFIX}{project_id}:thread:{thread_id}"

        try:
            cache = await self._cache()
            await cache.srem(active_threads_key, thread_id)
            await cache.delete(slot_key)
        except Exception as exc:
            self.logger.warning(
                "Failed to release project thread slot",
                extra={
                    "project_id": project_id,
                    "thread_id": thread_id,
                    "error_type": type(exc).__name__,
                },
            )
