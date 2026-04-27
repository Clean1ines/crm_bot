from typing import Protocol

from src.domain.project_plane.json_types import JsonValue
from src.domain.project_plane.memory_views import MemoryEntryView


class MemoryReaderPort(Protocol):
    async def get_for_user_view(
        self,
        project_id: str,
        client_id: str,
        *,
        limit: int,
    ) -> list[MemoryEntryView]: ...


class MemoryWriterPort(Protocol):
    async def update_by_key(
        self,
        *,
        project_id: str,
        client_id: str,
        key: str,
        value: JsonValue,
    ) -> None: ...
