from dataclasses import asdict, is_dataclass
from typing import Optional

from src.application.ports.client_port import ClientReaderPort
from src.application.ports.memory_port import MemoryReaderPort
from src.application.ports.thread_port import ThreadReadPort
from src.domain.project_plane.client_views import ClientDetailView, ClientListView


def _serialize_timestamp(value):
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _serialize_value(value):
    if is_dataclass(value):
        return {
            key: _serialize_value(item)
            for key, item in asdict(value).items()
        }
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, tuple):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {
            str(key): _serialize_value(item)
            for key, item in value.items()
        }
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


class ClientQueryService:
    def __init__(
        self,
        client_repo: ClientReaderPort,
        thread_read_repo: ThreadReadPort,
        memory_repo: MemoryReaderPort,
    ) -> None:
        self.client_repo = client_repo
        self.thread_read_repo = thread_read_repo
        self.memory_repo = memory_repo

    async def list_clients(
        self,
        project_id: str,
        *,
        limit: int,
        offset: int,
        search: Optional[str],
    ) -> dict:
        result: ClientListView = await self.client_repo.list_for_project_view(
            project_id,
            limit=limit,
            offset=offset,
            search=search,
        )
        return _serialize_value(result)

    async def get_client_detail(self, project_id: str, client_id: str) -> dict | None:
        result: ClientDetailView | None = await self.client_repo.get_by_id_view(project_id, client_id)
        if result is None:
            return None

        client = _serialize_value(result)
        if not isinstance(client, dict):
            return None

        memory = await self._load_memory_records(project_id, client_id, limit=100)
        client["memory"] = memory

        threads = await self.thread_read_repo.get_dialogs(project_id, client_id=client_id)
        client["threads"] = [_serialize_value(thread) for thread in threads]

        for thread in client["threads"]:
            if not isinstance(thread, dict):
                continue
            if thread.get("created_at"):
                thread["created_at"] = _serialize_timestamp(thread["created_at"])
            if thread.get("updated_at"):
                thread["updated_at"] = _serialize_timestamp(thread["updated_at"])
            if thread.get("id"):
                thread["id"] = str(thread["id"])

        return client

    async def _load_memory_records(
        self,
        project_id: str,
        client_id: str,
        *,
        limit: int,
    ) -> list[dict]:
        result = await self.memory_repo.get_for_user_view(project_id, client_id, limit=limit)
        return [_serialize_value(entry) for entry in result]
