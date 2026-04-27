from src.application.ports.memory_port import MemoryWriterPort
from src.application.ports.thread_port import ThreadLifecyclePort


class ThreadCommandService:
    def __init__(
        self,
        thread_lifecycle_repo: ThreadLifecyclePort,
        memory_repo: MemoryWriterPort,
    ) -> None:
        self.thread_lifecycle_repo = thread_lifecycle_repo
        self.memory_repo = memory_repo

    async def archive_thread(self, thread_id: str) -> dict[str, str]:
        await self.thread_lifecycle_repo.archive_thread(thread_id)
        return {"status": "archived"}

    async def save_memory(
        self,
        project_id: str,
        client_id: str,
        key: str,
        value: object,
    ) -> dict[str, str]:
        await self.memory_repo.update_by_key(
            project_id=project_id,
            client_id=client_id,
            key=key,
            value=value,
        )
        return {"status": "saved"}

    async def update_memory_entry(
        self,
        project_id: str,
        client_id: str,
        key: str,
        value: object,
    ) -> dict[str, str]:
        return await self.save_memory(
            project_id=project_id,
            client_id=client_id,
            key=key,
            value=value,
        )
