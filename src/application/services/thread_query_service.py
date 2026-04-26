from typing import Any

from src.application.ports.event_port import EventReaderPort
from src.application.ports.thread_port import (
    ThreadMessagePort,
    ThreadReadPort,
    ThreadRuntimeStatePort,
)


class ThreadQueryService:
    def __init__(
        self,
        thread_read_repo: ThreadReadPort,
        thread_message_repo: ThreadMessagePort,
        thread_runtime_state_repo: ThreadRuntimeStatePort,
        event_repo: EventReaderPort,
        memory_repo: Any,
    ) -> None:
        self.thread_read_repo = thread_read_repo
        self.thread_message_repo = thread_message_repo
        self.thread_runtime_state_repo = thread_runtime_state_repo
        self.event_repo = event_repo
        self.memory_repo = memory_repo

    async def list_dialogs(
        self,
        project_id: str,
        limit: int = 20,
        offset: int = 0,
        status_filter: str | None = None,
        search: str | None = None,
    ):
        return await self.thread_read_repo.get_dialogs(
            project_id,
            limit=limit,
            offset=offset,
            status_filter=status_filter,
            search=search,
        )

    async def get_thread_view(self, thread_id: str):
        return await self.thread_read_repo.get_thread_with_project_view(thread_id)

    async def get_thread(self, thread_id: str):
        return await self.get_thread_view(thread_id)

    async def get_messages(self, thread_id: str, limit: int, offset: int) -> dict:
        return {
            "messages": await self.thread_message_repo.get_messages(
                thread_id,
                limit,
                offset,
            )
        }

    async def get_timeline(self, thread_id: str, limit: int, offset: int) -> dict:
        events = await self.event_repo.list_for_stream(thread_id, limit=limit, offset=offset)
        return {"events": events}

    async def get_memory(self, project_id: str, client_id: str | None, *, limit: int = 100) -> dict:
        if not client_id:
            return {"items": []}

        if hasattr(self.memory_repo, "list_for_client"):
            items = await self.memory_repo.list_for_client(project_id, client_id, limit=limit)
        else:
            items = await self.memory_repo.get_for_client(project_id, client_id, limit=limit)

        return {"items": items}

    async def get_state(self, thread_id: str) -> dict:
        state = await self.thread_runtime_state_repo.get_state_json(thread_id) or {}
        return {"state": state}

    async def get_context(self, thread_id: str) -> dict:
        return await self.get_state(thread_id)
