"""
Manager reply orchestration.
"""

from typing import Optional

from src.domain.project_plane.manager_assignments import build_manager_audit_payload
from src.domain.project_plane.thread_runtime import ThreadRuntimeSnapshot
from src.domain.project_plane.thread_status import ThreadStatus


class ManagerReplyService:
    def __init__(
        self,
        *,
        projects,
        threads,
        telegram_client,
        event_emitter,
        logger,
    ) -> None:
        self.projects = projects
        self.threads = threads
        self.telegram_client = telegram_client
        self.event_emitter = event_emitter
        self.logger = logger

    async def resolve_manager_user_id_by_telegram(
        self,
        project_id: str,
        manager_chat_id: str,
    ) -> Optional[str]:
        return await self.projects.resolve_manager_user_id_by_telegram(project_id, manager_chat_id)

    async def resolve_manager_display_name(
        self,
        *,
        project_id: str,
        manager_chat_id: Optional[str],
        manager_user_id: Optional[str],
    ) -> str:
        if manager_chat_id:
            try:
                manager_bot_token = await self.projects.get_manager_bot_token(project_id)
                if manager_bot_token:
                    response = await self.telegram_client.post_json(
                        manager_bot_token,
                        "getChat",
                        {"chat_id": manager_chat_id},
                    )
                    if response.get("ok"):
                        chat_data = response.get("result") or {}
                        telegram_name = chat_data.get("first_name") or chat_data.get("username")
                        if telegram_name:
                            return telegram_name
            except Exception as exc:
                self.logger.warning("Failed to fetch manager name from Telegram", extra={"error": str(exc)})

        if manager_user_id:
            try:
                platform_name = await self.projects.get_user_display_name(manager_user_id)
                if platform_name:
                    return platform_name
            except Exception as exc:
                self.logger.warning("Failed to fetch manager name from platform profile", extra={"error": str(exc)})

        return "Manager"

    async def manager_reply(
        self,
        thread_id: str,
        manager_text: str,
        manager_chat_id: Optional[str] = None,
        manager_user_id: Optional[str] = None,
    ) -> bool:
        self.logger.info(
            "Sending manager reply",
            extra={
                "thread_id": thread_id,
                "manager_chat_id": manager_chat_id,
                "manager_user_id": manager_user_id,
            },
        )

        thread_view = await self.threads.get_thread_with_project_view(thread_id)
        thread_snapshot = ThreadRuntimeSnapshot.from_record(thread_view.to_record() if thread_view else None)
        if not thread_snapshot:
            raise ValueError(f"Thread {thread_id} not found")

        if thread_snapshot.status != ThreadStatus.MANUAL.value:
            raise ValueError(f"Thread {thread_id} status is {thread_snapshot.status}, expected MANUAL")

        project_id = thread_snapshot.project_id
        if not project_id:
            raise RuntimeError(f"Project id not found for thread {thread_id}")

        manager_name = await self.resolve_manager_display_name(
            project_id=project_id,
            manager_chat_id=manager_chat_id,
            manager_user_id=manager_user_id,
        )
        prefixed_text = f"[{manager_name}]: {manager_text}"

        await self.threads.append_manager_reply_message(thread_id, prefixed_text)

        bot_token = await self.projects.get_bot_token(project_id)
        if not bot_token:
            raise RuntimeError(f"Project {project_id} has no bot token")

        chat_id = thread_snapshot.chat_id
        if not chat_id:
            raise RuntimeError(f"Client chat_id not found for thread {thread_id}")

        response = await self.telegram_client.post_json(
            bot_token,
            "sendMessage",
            {
                "chat_id": chat_id,
                "text": prefixed_text,
            },
        )
        if response.get("ok") is False:
            self.logger.error(
                "Failed to send manager reply",
                extra={"thread_id": thread_id, "response": response},
            )
            raise RuntimeError("Telegram API error")

        await self.event_emitter.emit_event(
            stream_id=str(thread_id),
            project_id=project_id,
            event_type="manager_replied",
            payload={
                "text": manager_text,
                **build_manager_audit_payload(
                    manager_user_id=manager_user_id,
                    manager_chat_id=manager_chat_id,
                ),
            },
        )

        self.logger.info("Manager reply sent successfully", extra={"thread_id": thread_id})
        return True
