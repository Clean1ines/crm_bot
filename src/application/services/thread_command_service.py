from src.application.ports.memory_port import MemoryWriterPort
from src.application.ports.thread_port import ThreadWriterPort


class ThreadCommandService:
    def __init__(
        self,
        thread_repo: ThreadWriterPort,
        memory_repo: MemoryWriterPort,
    ) -> None:
        self.thread_repo = thread_repo
        self.memory_repo = memory_repo

    async def update_memory_entry(
        self,
        *,
        project_id: str,
        client_id: str,
        key: str,
        value,
    ) -> dict:
        await self.memory_repo.update_by_key(
            project_id=project_id,
            client_id=client_id,
            key=key,
            value=value,
        )
        return {"status": "updated"}
