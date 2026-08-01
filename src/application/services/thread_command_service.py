from uuid import UUID

from src.application.errors import ValidationError
from src.application.ports.memory_port import MemoryWriterPort
from src.application.ports.conversation_summary_port import TicketResolutionPayload
from src.application.ports.thread_port import ThreadLifecyclePort
from src.application.services.ticket_resolution_service import TicketResolutionService
from src.domain.control_plane.roles import PROJECT_ADMIN_ROLES
from src.domain.project_plane.json_types import JsonValue
from src.domain.project_plane.thread_status import ThreadStatus


class ThreadCommandService:
    def __init__(
        self,
        thread_lifecycle_repo: ThreadLifecyclePort,
        memory_repo: MemoryWriterPort,
        thread_read_repo=None,
        event_repo=None,
        project_access_service=None,
        user_repo=None,
        ticket_resolution_service: TicketResolutionService | None = None,
    ) -> None:
        self.thread_lifecycle_repo = thread_lifecycle_repo
        self.memory_repo = memory_repo
        self.thread_read_repo = thread_read_repo
        self.event_repo = event_repo
        self.project_access_service = project_access_service
        self.user_repo = user_repo
        self.ticket_resolution_service = ticket_resolution_service

    async def archive_thread(self, thread_id: str) -> dict[str, str]:
        await self.thread_lifecycle_repo.archive_thread(thread_id)
        return {"status": "archived"}

    async def save_memory(
        self,
        project_id: str,
        client_id: str,
        key: str,
        value: JsonValue,
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
        value: JsonValue,
    ) -> dict[str, str]:
        return await self.save_memory(
            project_id=project_id,
            client_id=client_id,
            key=key,
            value=value,
        )

    async def update_ticket_resolution(
        self,
        *,
        thread_id: str,
        summary_text: str,
        expected_version: int,
        actor_user_id: str,
    ) -> TicketResolutionPayload:
        return await self._resolution_service().edit(
            thread_id=thread_id,
            summary_text=summary_text,
            expected_version=expected_version,
            actor_user_id=actor_user_id,
        )

    async def regenerate_ticket_resolution(
        self, *, thread_id: str, actor_user_id: str
    ) -> TicketResolutionPayload:
        return await self._resolution_service().regenerate(
            thread_id=thread_id,
            actor_user_id=actor_user_id,
        )

    async def reset_dialog_by_telegram_admin(
        self,
        *,
        project_id: str,
        chat_id: int,
        actor_telegram_id: int,
        username: str | None = None,
        full_name: str | None = None,
    ) -> str:
        if self.user_repo is None or self.project_access_service is None:
            return "Сброс диалога временно недоступен."

        user_view = await self.user_repo.get_user_by_identity_view(
            "telegram",
            str(actor_telegram_id),
        )
        if user_view is None:
            return "Команда доступна только владельцу или администратору проекта."
        actor_user_id = str(user_view.id)
        actor_role = await self._reset_actor_role(project_id, actor_user_id)
        if actor_role is None:
            return "Команда доступна только владельцу или администратору проекта."

        client_id = await self.thread_lifecycle_repo.find_client(
            project_id,
            chat_id,
            source="telegram",
        )
        if client_id is None:
            return "Активный диалог не найден."
        thread_id = await self.thread_lifecycle_repo.get_active_thread(client_id)
        if thread_id is None:
            return "Активный диалог не найден."

        thread_view = None
        if self.thread_read_repo is not None:
            thread_view = await self.thread_read_repo.get_thread_with_project_view(
                str(thread_id)
            )
        status = getattr(thread_view, "status", None) if thread_view else None
        if status in {ThreadStatus.WAITING_MANAGER.value, ThreadStatus.MANUAL.value}:
            return (
                "Диалог сейчас передан менеджеру. "
                "Сначала закройте обращение обычным способом."
            )

        await self.thread_lifecycle_repo.update_status(
            str(thread_id),
            ThreadStatus.CLOSED.value,
        )
        if self.event_repo is not None:
            await self.event_repo.append(
                stream_id=UUID(str(thread_id)),
                project_id=UUID(project_id),
                event_type="dialog_reset",
                payload={
                    "actor_user_id": actor_user_id,
                    "actor_role": actor_role,
                    "project_id": project_id,
                    "thread_id": str(thread_id),
                    "reason": "admin_test_reset",
                },
            )
        return "Диалог сброшен. Следующее сообщение начнёт новый диалог."

    async def _reset_actor_role(
        self, project_id: str, actor_user_id: str
    ) -> str | None:
        is_platform_admin = getattr(self.user_repo, "is_platform_admin", None)
        if is_platform_admin is not None and await is_platform_admin(actor_user_id):
            return "platform_admin"

        role = await self.project_access_service.resolve_effective_project_role(
            project_id,
            actor_user_id,
        )
        if role in PROJECT_ADMIN_ROLES:
            return str(role)
        return None

    def _resolution_service(self) -> TicketResolutionService:
        if self.ticket_resolution_service is None:
            raise ValidationError("ticket resolution service is not configured")
        return self.ticket_resolution_service
