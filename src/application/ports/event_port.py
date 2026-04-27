from typing import Protocol

from src.domain.project_plane.event_views import EventTimelineItemView
from src.domain.project_plane.manager_reply_history import ManagerReplyHistoryItemView


class EventReaderPort(Protocol):
    async def get_events_for_thread(
        self,
        thread_id: str,
        limit: int,
        offset: int,
    ) -> list[EventTimelineItemView]: ...

    async def get_manager_reply_history(
        self,
        project_id: str,
        manager_user_id: str,
        limit: int,
        offset: int,
    ) -> list[ManagerReplyHistoryItemView]: ...
