from typing import Protocol


class EventReaderPort(Protocol):
    async def get_events_for_thread(self, thread_id: str, limit: int, offset: int) -> list[dict]: ...
