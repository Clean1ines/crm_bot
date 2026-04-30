from __future__ import annotations

from src.application.ports.cache_port import CachePort
from src.application.ports.manager_bot_port import ManagerBotOrchestratorPort
from src.domain.project_plane.manager_assignments import (
    ManagerActor,
    ManagerReplySession,
)


MANAGER_CLAIM_IDLE_TIMEOUT_SECONDS = 15 * 60


class TicketCommandService:
    def __init__(
        self,
        orchestrator: ManagerBotOrchestratorPort,
        cache: CachePort,
    ) -> None:
        self.orchestrator = orchestrator
        self.cache = cache

    async def claim_ticket(
        self,
        *,
        thread_id: str,
        manager_user_id: str,
    ) -> dict[str, str]:
        session = ManagerReplySession.for_platform_manager(
            thread_id=thread_id,
            manager_user_id=manager_user_id,
        )
        await self.cache.setex(
            session.thread_key,
            MANAGER_CLAIM_IDLE_TIMEOUT_SECONDS,
            session.to_redis_value(),
        )
        await self.orchestrator.claim_thread_for_manager(
            thread_id,
            manager=ManagerActor(user_id=manager_user_id),
        )
        return {"status": "claimed"}

    async def close_ticket(self, *, thread_id: str) -> dict[str, str]:
        raw_session = await self.cache.get(f"awaiting_reply_thread:{thread_id}")
        session = ManagerReplySession.from_redis_value(
            thread_id=thread_id,
            raw_value=raw_session,
        )
        if session is not None and session.manager_key:
            await self.cache.delete(session.manager_key)
        await self.cache.delete(f"awaiting_reply_thread:{thread_id}")
        await self.orchestrator.close_thread_for_manager(thread_id)
        return {"status": "closed"}

    async def mark_ticket_replied(
        self,
        *,
        thread_id: str,
        manager_user_id: str,
    ) -> None:
        session = ManagerReplySession.for_platform_manager(
            thread_id=thread_id,
            manager_user_id=manager_user_id,
            has_manager_reply=True,
        )
        await self.cache.set(session.thread_key, session.to_redis_value())
