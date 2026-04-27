from collections.abc import Awaitable
from typing import Protocol


CacheValue = str | bytes | None


class CachePort(Protocol):
    async def get(self, key: str) -> CacheValue: ...

    async def expire(self, key: str, seconds: int) -> bool: ...

    async def exists(self, key: str) -> int: ...

    async def sadd(self, key: str, value: str) -> int: ...

    async def set(self, key: str, value: str, ex: int | None = None) -> bool | None: ...

    async def setex(self, key: str, seconds: int, value: str) -> bool | None: ...

    async def srem(self, key: str, value: str) -> int: ...

    async def delete(self, key: str) -> int: ...


class RateLimitCachePort(CachePort, Protocol):
    async def incr(self, key: str) -> int: ...

    async def scard(self, key: str) -> int: ...


class RuntimeCachePort(RateLimitCachePort, Protocol):
    """Cache surface required by project runtime guards."""


class CacheFactoryPort(Protocol):
    def __call__(self) -> Awaitable[RuntimeCachePort]: ...


class NullCache:
    async def get(self, key: str) -> CacheValue:
        return None

    async def incr(self, key: str) -> int:
        return 1

    async def expire(self, key: str, seconds: int) -> bool:
        return False

    async def exists(self, key: str) -> int:
        return 0

    async def sadd(self, key: str, value: str) -> int:
        return 0

    async def set(self, key: str, value: str, ex: int | None = None) -> bool:
        return False

    async def setex(self, key: str, seconds: int, value: str) -> bool:
        return False

    async def scard(self, key: str) -> int:
        return 0

    async def srem(self, key: str, value: str) -> int:
        return 0

    async def delete(self, key: str) -> int:
        return 0
