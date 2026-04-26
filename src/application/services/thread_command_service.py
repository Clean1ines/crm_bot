from typing import Any

from src.application.ports.thread_port import ThreadLifecyclePort


class ThreadCommandService:
    def __init__(
        self,
        thread_lifecycle_repo: ThreadLifecyclePort,
        memory_repo: Any,
    ) -> None:
        self.thread_lifecycle_repo = thread_lifecycle_repo
        self.memory_repo = memory_repo

    async def update_memory_entry(
        self,
        *,
        project_id: str,
        client_id: str,
        key: str,
        value: Any,
    ) -> dict:
        if hasattr(self.memory_repo, "set"):
            await self.memory_repo.set(
                project_id=project_id,
                client_id=client_id,
                key=key,
                value=value,
                type_="user_edited",
            )
            return {"status": "updated"}

        return await self.memory_repo.update_entry(
            project_id=project_id,
            client_id=client_id,
            key=key,
            value=value,
        )
