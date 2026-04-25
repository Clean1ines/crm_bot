from src.domain.project_plane.thread_views import ThreadWithProjectView
from src.application.ports.event_port import EventReaderPort
from src.application.ports.memory_port import MemoryReaderPort
from src.application.ports.thread_port import ThreadReaderPort


class ThreadQueryService:
    def __init__(
        self,
        thread_repo: ThreadReaderPort,
        event_repo: EventReaderPort,
        memory_repo: MemoryReaderPort,
    ) -> None:
        self.thread_repo = thread_repo
        self.event_repo = event_repo
        self.memory_repo = memory_repo

    async def list_dialogs(
        self,
        *,
        project_id: str,
        limit: int,
        offset: int,
        status_filter: str | None,
        search: str | None,
    ) -> list[dict]:
        return await self.thread_repo.get_dialogs(
            project_id=project_id,
            limit=limit,
            offset=offset,
            status_filter=status_filter,
            search=search,
        )

    async def get_thread_view(self, thread_id: str) -> ThreadWithProjectView | None:
        return await self.thread_repo.get_thread_with_project_view(thread_id)

    async def get_messages(self, thread_id: str, limit: int, offset: int) -> dict:
        return {"messages": await self.thread_repo.get_messages(thread_id, limit, offset)}

    async def get_timeline(self, thread_id: str, limit: int, offset: int) -> dict:
        return {"events": await self.event_repo.get_events_for_thread(thread_id, limit, offset)}

    async def get_memory(self, project_id: str, client_id: str | None, *, limit: int = 100) -> dict:
        if not client_id:
            return {"memory": []}

        result = await self.memory_repo.get_for_user_view(
            project_id=project_id,
            client_id=client_id,
            limit=limit,
        )
        return {"memory": [entry.to_record() for entry in result]}

    async def get_state(self, thread_id: str) -> dict:
        state = await self.thread_repo.get_state_json(thread_id) or {}
        return {"state": dict(state)}
