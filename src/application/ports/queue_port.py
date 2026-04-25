from __future__ import annotations

from typing import Protocol


class QueueRepositoryPort(Protocol):
    async def enqueue(self, *, task_type: str, payload: object) -> str: ...
