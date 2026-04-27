from src.application.ports.event_port import EventReaderPort
from src.domain.project_plane.json_types import JsonObject
from src.application.errors import NotFoundError, ValidationError
from src.application.ports.memory_port import MemoryReaderPort
from src.application.ports.project_port import ProjectAccessPort
from src.application.ports.thread_port import (
    ThreadMessagePort,
    ThreadReadPort,
    ThreadRuntimeStatePort,
)
from src.domain.control_plane.roles import PROJECT_READ_ROLES, PROJECT_WRITE_ROLES


def _event_record(event) -> JsonObject:
    return {
        "id": event.id,
        "type": event.type,
        "payload": event.payload,
        "ts": event.ts,
        "stream_id": event.stream_id,
    }


class ThreadQueryService:
    def __init__(
        self,
        thread_read_repo: ThreadReadPort,
        thread_message_repo: ThreadMessagePort,
        thread_runtime_state_repo: ThreadRuntimeStatePort,
        event_repo: EventReaderPort,
        memory_repo: MemoryReaderPort,
        access_service: ProjectAccessPort,
    ) -> None:
        self.thread_read_repo = thread_read_repo
        self.thread_message_repo = thread_message_repo
        self.thread_runtime_state_repo = thread_runtime_state_repo
        self.event_repo = event_repo
        self.memory_repo = memory_repo
        self.access_service = access_service

    async def list_dialogs(
        self,
        project_id: str,
        limit: int = 20,
        offset: int = 0,
        status_filter: str | None = None,
        search: str | None = None,
        current_user_id: str | None = None,
    ):
        if current_user_id is not None:
            await self.access_service.require_project_role(
                project_id, current_user_id, PROJECT_READ_ROLES
            )

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

    async def require_thread_access(
        self,
        thread_id: str,
        current_user_id: str,
        allowed_roles: list[str],
    ):
        thread = await self.get_thread_view(thread_id)
        if not thread:
            raise NotFoundError("Thread not found")
        if not thread.project_id:
            raise NotFoundError("Thread not found")

        await self.access_service.require_project_role(
            thread.project_id,
            current_user_id,
            allowed_roles,
        )
        return thread

    async def get_messages_for_user(
        self,
        thread_id: str,
        current_user_id: str,
        limit: int,
        offset: int,
    ) -> dict:
        await self.require_thread_access(thread_id, current_user_id, PROJECT_READ_ROLES)
        return await self.get_messages(thread_id, limit, offset)

    async def get_timeline_for_user(
        self,
        thread_id: str,
        current_user_id: str,
        limit: int,
        offset: int,
    ) -> dict:
        await self.require_thread_access(thread_id, current_user_id, PROJECT_READ_ROLES)
        return await self.get_timeline(thread_id, limit, offset)

    async def get_memory_for_user(
        self,
        thread_id: str,
        current_user_id: str,
        *,
        limit: int = 100,
    ) -> dict:
        thread = await self.require_thread_access(
            thread_id, current_user_id, PROJECT_READ_ROLES
        )
        return await self.get_memory(thread.project_id, thread.client_id, limit=limit)

    async def get_state_for_user(self, thread_id: str, current_user_id: str) -> dict:
        await self.require_thread_access(thread_id, current_user_id, PROJECT_READ_ROLES)
        return await self.get_state(thread_id)

    async def get_manual_reply_thread_for_user(
        self, thread_id: str, current_user_id: str
    ):
        thread = await self.require_thread_access(
            thread_id, current_user_id, PROJECT_WRITE_ROLES
        )
        if thread.status != "manual":
            raise ValidationError("Thread is not in manual mode")
        return thread

    async def get_memory_update_target_for_user(
        self, thread_id: str, current_user_id: str
    ):
        thread = await self.require_thread_access(
            thread_id, current_user_id, PROJECT_READ_ROLES
        )
        if not thread.client_id:
            raise ValidationError("No client associated with thread")
        return thread

    async def get_messages(self, thread_id: str, limit: int, offset: int) -> dict:
        return {
            "messages": await self.thread_message_repo.get_messages(
                thread_id,
                limit,
                offset,
            )
        }

    async def get_timeline(self, thread_id: str, limit: int, offset: int) -> dict:
        events = await self.event_repo.get_events_for_thread(thread_id, limit, offset)
        return {"events": [_event_record(event) for event in events]}

    async def get_memory(
        self, project_id: str, client_id: str | None, *, limit: int = 100
    ) -> dict:
        if not client_id:
            return {"items": []}

        if hasattr(self.memory_repo, "list_for_client"):
            items = await self.memory_repo.list_for_client(
                project_id, client_id, limit=limit
            )
        else:
            items = await self.memory_repo.get_for_client(
                project_id, client_id, limit=limit
            )

        return {"items": items}

    async def get_state(self, thread_id: str) -> dict:
        state = await self.thread_runtime_state_repo.get_state_json(thread_id) or {}
        return {"state": state}

    async def get_context(self, thread_id: str) -> dict:
        return await self.get_state(thread_id)
