"""
Manager reply orchestration.
"""

from src.domain.project_plane.manager_assignments import build_manager_audit_payload
from src.domain.project_plane.thread_runtime import ThreadRuntimeSnapshot
from src.domain.project_plane.thread_status import ThreadStatus


MANAGER_FALLBACK_NAME = "Manager"


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
    ) -> str | None:
        return await self.projects.resolve_manager_user_id_by_telegram(
            project_id, manager_chat_id
        )

    async def resolve_manager_display_name(
        self,
        *,
        project_id: str,
        manager_chat_id: str | None,
        manager_user_id: str | None,
    ) -> str:
        return (
            await self._platform_manager_display_name(manager_user_id)
            or await self._telegram_manager_display_name(project_id, manager_chat_id)
            or MANAGER_FALLBACK_NAME
        )

    async def manager_reply(
        self,
        thread_id: str,
        manager_text: str,
        manager_chat_id: str | None = None,
        manager_user_id: str | None = None,
    ) -> bool:
        self._log_manager_reply_started(
            thread_id=thread_id,
            manager_chat_id=manager_chat_id,
            manager_user_id=manager_user_id,
        )

        thread_snapshot = await self._load_manual_thread_snapshot(thread_id)
        project_id = self._require_project_id(thread_snapshot, thread_id)
        resolved_manager_user_id = await self._resolve_required_manager_user_id(
            project_id=project_id,
            thread_id=thread_id,
            thread_snapshot=thread_snapshot,
            manager_chat_id=manager_chat_id,
            manager_user_id=manager_user_id,
        )

        prefixed_text = await self._prefixed_manager_text(
            project_id=project_id,
            manager_chat_id=manager_chat_id,
            manager_user_id=resolved_manager_user_id,
            manager_text=manager_text,
        )

        await self.threads.append_manager_reply_message(thread_id, prefixed_text)
        await self._send_reply_to_client(
            project_id=project_id,
            thread_id=thread_id,
            chat_id=thread_snapshot.chat_id,
            text=prefixed_text,
        )
        await self._emit_manager_reply_event(
            thread_id=thread_id,
            project_id=project_id,
            manager_text=manager_text,
            manager_user_id=resolved_manager_user_id,
            manager_chat_id=manager_chat_id,
        )

        self.logger.info(
            "Manager reply sent successfully", extra={"thread_id": thread_id}
        )
        return True

    def _log_manager_reply_started(
        self,
        *,
        thread_id: str,
        manager_chat_id: str | None,
        manager_user_id: str | None,
    ) -> None:
        self.logger.info(
            "Sending manager reply",
            extra={
                "thread_id": thread_id,
                "manager_chat_id": manager_chat_id,
                "manager_user_id": manager_user_id,
            },
        )

    async def _platform_manager_display_name(
        self, manager_user_id: str | None
    ) -> str | None:
        if not manager_user_id:
            return None

        try:
            return await self.projects.get_user_display_name(manager_user_id)
        except Exception as exc:
            self.logger.warning(
                "Failed to fetch manager name from platform profile",
                extra={"error": str(exc)},
            )
            return None

    async def _telegram_manager_display_name(
        self,
        project_id: str,
        manager_chat_id: str | None,
    ) -> str | None:
        if not manager_chat_id:
            return None

        try:
            return await self._telegram_chat_display_name(project_id, manager_chat_id)
        except Exception as exc:
            self.logger.warning(
                "Failed to fetch manager name from Telegram",
                extra={"error": str(exc)},
            )
            return None

    async def _telegram_chat_display_name(
        self,
        project_id: str,
        manager_chat_id: str,
    ) -> str | None:
        manager_bot_token = await self.projects.get_manager_bot_token(project_id)
        if not manager_bot_token:
            return None

        response = await self.telegram_client.post_json(
            manager_bot_token,
            "getChat",
            {"chat_id": manager_chat_id},
        )
        if not response.get("ok"):
            return None

        chat_data = response.get("result") or {}
        return chat_data.get("first_name") or chat_data.get("username")

    async def _load_manual_thread_snapshot(
        self, thread_id: str
    ) -> ThreadRuntimeSnapshot:
        thread_snapshot = await self._load_thread_snapshot(thread_id)
        if thread_snapshot.status != ThreadStatus.MANUAL.value:
            raise ValueError(
                f"Thread {thread_id} status is {thread_snapshot.status}, expected MANUAL"
            )
        return thread_snapshot

    async def _load_thread_snapshot(self, thread_id: str) -> ThreadRuntimeSnapshot:
        thread_view = await self.threads.get_thread_with_project_view(thread_id)
        thread_snapshot = ThreadRuntimeSnapshot.from_record(
            thread_view.to_record() if thread_view else None
        )
        if not thread_snapshot:
            raise ValueError(f"Thread {thread_id} not found")
        return thread_snapshot

    def _require_project_id(
        self, thread_snapshot: ThreadRuntimeSnapshot, thread_id: str
    ) -> str:
        if not thread_snapshot.project_id:
            raise RuntimeError(f"Project id not found for thread {thread_id}")
        return thread_snapshot.project_id

    async def _resolve_required_manager_user_id(
        self,
        *,
        project_id: str,
        thread_id: str,
        thread_snapshot: ThreadRuntimeSnapshot,
        manager_chat_id: str | None,
        manager_user_id: str | None,
    ) -> str:
        resolved_manager_user_id = await self._resolve_manager_user_id(
            project_id=project_id,
            thread_snapshot=thread_snapshot,
            manager_chat_id=manager_chat_id,
            manager_user_id=manager_user_id,
        )
        if not resolved_manager_user_id:
            raise PermissionError(
                "Canonical manager_user_id is required for manager replies"
            )
        return resolved_manager_user_id

    async def _resolve_manager_user_id(
        self,
        *,
        project_id: str,
        thread_snapshot: ThreadRuntimeSnapshot,
        manager_chat_id: str | None,
        manager_user_id: str | None,
    ) -> str | None:
        if manager_user_id:
            return manager_user_id
        if thread_snapshot.manager_user_id:
            return thread_snapshot.manager_user_id
        if manager_chat_id:
            return await self.resolve_manager_user_id_by_telegram(
                project_id, manager_chat_id
            )
        return None

    async def _prefixed_manager_text(
        self,
        *,
        project_id: str,
        manager_chat_id: str | None,
        manager_user_id: str,
        manager_text: str,
    ) -> str:
        manager_name = await self.resolve_manager_display_name(
            project_id=project_id,
            manager_chat_id=manager_chat_id,
            manager_user_id=manager_user_id,
        )
        return f"[{manager_name}]: {manager_text}"

    async def _send_reply_to_client(
        self,
        *,
        project_id: str,
        thread_id: str,
        chat_id: str | None,
        text: str,
    ) -> None:
        bot_token = await self._require_bot_token(project_id)
        client_chat_id = self._require_client_chat_id(chat_id, thread_id)

        response = await self.telegram_client.post_json(
            bot_token,
            "sendMessage",
            {
                "chat_id": client_chat_id,
                "text": text,
            },
        )
        self._ensure_telegram_response_ok(thread_id, response)

    async def _require_bot_token(self, project_id: str) -> str:
        bot_token = await self.projects.get_bot_token(project_id)
        if not bot_token:
            raise RuntimeError(f"Project {project_id} has no bot token")
        return bot_token

    def _require_client_chat_id(self, chat_id: str | None, thread_id: str) -> str:
        if not chat_id:
            raise RuntimeError(f"Client chat_id not found for thread {thread_id}")
        return chat_id

    def _ensure_telegram_response_ok(
        self, thread_id: str, response: dict[str, object]
    ) -> None:
        if response.get("ok") is not False:
            return

        self.logger.error(
            "Failed to send manager reply",
            extra={"thread_id": thread_id, "response": response},
        )
        raise RuntimeError("Telegram API error")

    async def _emit_manager_reply_event(
        self,
        *,
        thread_id: str,
        project_id: str,
        manager_text: str,
        manager_user_id: str,
        manager_chat_id: str | None,
    ) -> None:
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
