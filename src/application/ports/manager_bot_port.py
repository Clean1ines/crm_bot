from __future__ import annotations

from typing import Protocol

from src.domain.project_plane.manager_assignments import ManagerActor
from src.domain.project_plane.thread_views import ThreadWithProjectView
from src.domain.project_plane.json_types import JsonObject


class ManagerThreadCoordinatorPort(Protocol):
    async def claim_for_manager(
        self,
        thread_id: str,
        *,
        manager: ManagerActor | None = None,
        manager_user_id: str | None = None,
        manager_chat_id: str | None = None,
    ) -> None: ...

    async def release_manager_assignment(self, thread_id: str) -> None: ...

    async def update_analytics(
        self,
        thread_id: str,
        intent: str | None = None,
        lifecycle: str | None = None,
        cta: str | None = None,
        decision: str | None = None,
    ) -> None: ...

    async def get_thread_with_project_view(
        self, thread_id: str
    ) -> ThreadWithProjectView | None: ...


class ManagerMemoryResetPort(Protocol):
    async def set_lifecycle(
        self, project_id: str, client_id: str, lifecycle: str
    ) -> None: ...

    async def set(
        self,
        project_id: str,
        client_id: str,
        key: str,
        value: JsonObject,
        type_: str,
    ) -> None: ...


class ManagerBotOrchestratorPort(Protocol):
    threads: ManagerThreadCoordinatorPort
    memory_repo: ManagerMemoryResetPort | None

    async def resolve_manager_user_id_by_telegram(
        self,
        project_id: str,
        manager_chat_id: str,
    ) -> str | None: ...

    async def manager_reply(
        self,
        thread_id: str,
        text: str,
        manager_chat_id: str,
        *,
        manager_user_id: str | None = None,
    ) -> bool: ...
