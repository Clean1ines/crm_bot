from typing import Protocol

from src.domain.project_plane.json_types import JsonObject

from src.domain.project_plane.manager_assignments import ManagerActor
from src.domain.project_plane.thread_status import ThreadStatus
from src.domain.project_plane.thread_views import (
    ThreadAnalyticsView,
    ThreadDialogView,
    ThreadMessageCounts,
    ThreadMessageView,
    ThreadRuntimeMessageView,
    ThreadStatusSummaryView,
    ThreadWithProjectView,
)


class ThreadLifecyclePort(Protocol):
    async def get_or_create_client(
        self,
        project_id: str,
        chat_id: int,
        username: str | None = None,
        source: str = "telegram",
        full_name: str | None = None,
    ) -> str: ...

    async def get_active_thread(self, client_id: str) -> str | None: ...

    async def create_thread(self, client_id: str) -> str: ...

    async def update_status(
        self, thread_id: str, status: ThreadStatus | str
    ) -> None: ...

    async def update_interaction_mode(self, thread_id: str, mode: str) -> None: ...

    async def claim_for_manager(
        self,
        thread_id: str,
        *,
        manager: ManagerActor | None = None,
        manager_user_id: str | None = None,
        manager_chat_id: str | None = None,
    ) -> None: ...

    async def release_manager_assignment(self, thread_id: str) -> None: ...


class ThreadMessagePort(Protocol):
    async def add_message(self, thread_id: str, role: str, content: str) -> None: ...

    async def append_manager_reply_message(
        self, thread_id: str, content: str
    ) -> None: ...

    async def get_messages_for_langgraph(
        self, thread_id: str
    ) -> list[ThreadRuntimeMessageView]: ...

    async def get_messages(
        self,
        thread_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[ThreadMessageView]: ...


class ThreadRuntimeStatePort(Protocol):
    async def update_summary(self, thread_id: str, summary: str) -> None: ...

    async def get_state_json(self, thread_id: str) -> JsonObject | None: ...

    async def save_state_json(self, thread_id: str, state: JsonObject) -> None: ...

    async def update_analytics(
        self,
        thread_id: str,
        intent: str | None = None,
        lifecycle: str | None = None,
        cta: str | None = None,
        decision: str | None = None,
    ) -> None: ...

    async def get_analytics_view(
        self, thread_id: str
    ) -> ThreadAnalyticsView | None: ...

    async def get_message_counts_view(self, thread_id: str) -> ThreadMessageCounts: ...


class ThreadReadPort(Protocol):
    async def get_thread_with_project_view(
        self, thread_id: str
    ) -> ThreadWithProjectView | None: ...

    async def get_dialogs(
        self,
        project_id: str,
        limit: int = 20,
        offset: int = 0,
        status_filter: str | None = None,
        search: str | None = None,
    ) -> list[ThreadDialogView]: ...

    async def find_by_status(self, status: str) -> list[ThreadStatusSummaryView]: ...
