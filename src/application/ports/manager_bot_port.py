from __future__ import annotations

from typing import Protocol

from src.domain.project_plane.manager_assignments import ManagerActor


class ManagerBotOrchestratorPort(Protocol):
    async def resolve_manager_user_id_by_telegram(
        self,
        project_id: str,
        manager_chat_id: str,
    ) -> str | None: ...

    async def claim_thread_for_manager(
        self,
        thread_id: str,
        *,
        manager: ManagerActor,
    ) -> None: ...

    async def close_thread_for_manager(self, thread_id: str) -> None: ...

    async def manager_reply(
        self,
        thread_id: str,
        text: str,
        manager_chat_id: str,
        *,
        manager_user_id: str | None = None,
    ) -> bool: ...
