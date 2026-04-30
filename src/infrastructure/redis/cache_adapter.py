from collections.abc import Awaitable
import inspect

import redis.asyncio as redis

from src.application.ports.cache_port import CachePort


class RedisCacheAdapter(CachePort):
    def __init__(self, client: redis.Redis) -> None:
        self._client = client

    async def _resolve_int(self, value: Awaitable[object] | object) -> int:
        if inspect.isawaitable(value):
            resolved = await value
        else:
            resolved = value

        if isinstance(resolved, bool):
            return int(resolved)
        if isinstance(resolved, int):
            return resolved
        if isinstance(resolved, float):
            return int(resolved)
        if isinstance(resolved, str):
            return int(resolved)
        raise TypeError(f"Unexpected Redis integer response type: {type(resolved)!r}")

    async def get(self, key: str) -> str | bytes | None:
        value = await self._client.get(key)
        if isinstance(value, str | bytes):
            return value
        return None

    async def expire(self, key: str, seconds: int) -> bool:
        return bool(await self._client.expire(key, seconds))

    async def exists(self, key: str) -> int:
        return int(await self._client.exists(key))

    async def sadd(self, key: str, value: str) -> int:
        return await self._resolve_int(self._client.sadd(key, value))

    async def set(self, key: str, value: str, ex: int | None = None) -> bool | None:
        result = await self._client.set(key, value, ex=ex)
        return bool(result) if result is not None else None

    async def setex(self, key: str, seconds: int, value: str) -> bool | None:
        result = await self._client.setex(key, seconds, value)
        return bool(result) if result is not None else None

    async def srem(self, key: str, value: str) -> int:
        return await self._resolve_int(self._client.srem(key, value))

    async def delete(self, key: str) -> int:
        return int(await self._client.delete(key))
