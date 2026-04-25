from typing import Protocol


class ThreadLockPort(Protocol):
    async def acquire_thread_lock(self, thread_id: str) -> bool: ...
    async def release_thread_lock(self, thread_id: str) -> None: ...


class NullThreadLock:
    async def acquire_thread_lock(self, thread_id: str) -> bool:
        return True

    async def release_thread_lock(self, thread_id: str) -> None:
        return None
