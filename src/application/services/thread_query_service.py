from src.application.ports.event_port import EventReaderPort
from src.application.dto.thread_dto import (
    ThreadInspectorStateDto,
    ThreadTimelineItemDto,
)
from src.domain.project_plane.json_types import JsonObject
from src.domain.project_plane.thread_views import (
    ThreadAnalyticsView,
    ThreadMessageCounts,
    ThreadWithProjectView,
)
from src.application.errors import NotFoundError, ValidationError
from src.application.ports.memory_port import MemoryReaderPort
from src.application.ports.project_port import ProjectAccessPort
from src.application.ports.thread_port import (
    ThreadMessagePort,
    ThreadReadPort,
    ThreadRuntimeStatePort,
)
from src.domain.control_plane.roles import PROJECT_MANAGER_ROLES, PROJECT_READ_ROLES


def _event_record(event) -> JsonObject:
    return ThreadTimelineItemDto.from_event(event).to_record()


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
            thread_id, current_user_id, PROJECT_MANAGER_ROLES
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
            return {"items": [], "memory": []}

        items = await self.memory_repo.get_for_user_view(
            project_id,
            client_id,
            limit=limit,
        )

        return {"items": items, "memory": items}

    async def get_state(self, thread_id: str) -> dict:
        persisted_state = await self.thread_runtime_state_repo.get_state_json(thread_id)
        thread_view_raw = await self.thread_read_repo.get_thread_with_project_view(
            thread_id
        )
        analytics_view_raw = await self.thread_runtime_state_repo.get_analytics_view(
            thread_id
        )
        message_counts_raw = (
            await self.thread_runtime_state_repo.get_message_counts_view(thread_id)
        )
        thread_view = _thread_view(thread_view_raw)
        analytics_view = _analytics_view(analytics_view_raw)
        message_counts = _message_counts(message_counts_raw)
        return ThreadInspectorStateDto.create(
            persisted_state=persisted_state,
            thread_view=thread_view,
            analytics_view=analytics_view,
            message_counts=message_counts,
        ).to_record()

    async def get_context(self, thread_id: str) -> dict:
        return await self.get_state(thread_id)


def _thread_view(value: object) -> ThreadWithProjectView | None:
    if isinstance(value, ThreadWithProjectView):
        return value
    if isinstance(value, dict):
        return ThreadWithProjectView.from_record(value)
    return None


def _analytics_view(value: object) -> ThreadAnalyticsView | None:
    if isinstance(value, ThreadAnalyticsView):
        return value
    if isinstance(value, dict):
        return ThreadAnalyticsView.from_record(value)
    return None


def _message_counts(value: object) -> ThreadMessageCounts:
    if isinstance(value, ThreadMessageCounts):
        return value
    if isinstance(value, dict):
        return ThreadMessageCounts.from_record(value)
    return ThreadMessageCounts()
