from __future__ import annotations

from typing import Protocol

from src.domain.project_plane.json_types import JsonObject


class QueueRepositoryPort(Protocol):
    async def enqueue(self, *, task_type: str, payload: JsonObject) -> str: ...
