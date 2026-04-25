from typing import Protocol, Any


class MemoryReaderPort(Protocol):
    async def get_for_user_view(self, project_id: str, client_id: str, *, limit: int) -> list[Any]: ...


class MemoryWriterPort(Protocol):
    async def update_by_key(self, *, project_id: str, client_id: str, key: str, value: object) -> None: ...
