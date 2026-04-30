"""
Manager reply orchestration.
"""

from src.application.errors import InternalServiceError
from src.domain.display_names import build_display_name
from src.domain.project_plane.json_types import json_object_from_unknown
from src.domain.project_plane.manager_assignments import (
    ManagerActor,
    build_manager_audit_payload,
)
from src.domain.project_plane.thread_runtime import ThreadRuntimeSnapshot
from src.domain.project_plane.thread_status import ThreadStatus
from src.domain.runtime.dialog_state import default_dialog_state


MANAGER_FALLBACK_NAME = "Manager"


class ManagerReplyService:
    def __init__(
        self,
        *,
        projects,
        threads,
        thread_messages=None,
        thread_read=None,
        thread_runtime_state=None,
        memory_repo=None,
        telegram_client,
        event_emitter,
        logger,
    ) -> None:
        self.projects = projects
        self.threads = threads
        self.thread_messages = thread_messages or threads
        self.thread_read = thread_read or threads
        self.thread_runtime_state = thread_runtime_state
        self.memory_repo = memory_repo
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

    async def claim_thread_for_manager(
        self,
        thread_id: str,
        *,
        manager: ManagerActor,
    ) -> None:
        await self.threads.claim_for_manager(thread_id, manager=manager)
        claimed_thread = await self._load_manual_thread_snapshot(thread_id)
        if claimed_thread.manager_user_id != manager.user_id:
            raise ValueError(
                f"Thread {thread_id} claim was not persisted for manager {manager.user_id}"
            )
        try:
            await self._emit_manager_claimed_event(thread_id=thread_id, manager=manager)
        except Exception as exc:
            self.logger.warning(
                "Failed to emit manager claim event",
                extra={"thread_id": thread_id, "error": str(exc)},
            )

    async def close_thread_for_manager(
        self,
        thread_id: str,
        *,
        manually_closed: bool = True,
        close_reason: str | None = None,
    ) -> None:
        await self.threads.close_manager_ticket(thread_id)

        try:
            await self._reset_thread_analytics(thread_id)
        except Exception as exc:
            self.logger.warning(
                "Failed to reset thread analytics", extra={"error": str(exc)}
            )

        try:
            await self._reset_user_memory_after_ticket_closure(thread_id)
        except Exception as exc:
            self.logger.warning(
                "Failed to reset user memory after ticket closure",
                extra={"error": str(exc)},
            )

        try:
            await self._emit_ticket_closed_event(
                thread_id=thread_id,
                manually_closed=manually_closed,
                close_reason=close_reason,
            )
        except Exception as exc:
            self.logger.warning(
                "Failed to emit ticket closure event",
                extra={"error": str(exc)},
            )

    async def _reset_thread_analytics(self, thread_id: str) -> None:
        if self.thread_runtime_state is None:
            return

        await self.thread_runtime_state.update_analytics(
            thread_id=thread_id,
            lifecycle="active_client",
            decision=None,
            intent=None,
            cta=None,
        )
        self.logger.info(
            "Thread analytics reset after ticket closure",
            extra={"thread_id": thread_id},
        )

    async def _reset_user_memory_after_ticket_closure(self, thread_id: str) -> None:
        if self.memory_repo is None:
            return

        thread = await self.thread_read.get_thread_with_project_view(thread_id)
        if not thread:
            return

        client_id = thread.client_id
        project_id = thread.project_id
        if not client_id or not project_id:
            return

        await self.memory_repo.set_lifecycle(project_id, client_id, "active_client")
        await self.memory_repo.set(
            project_id,
            client_id,
            "dialog_state",
            json_object_from_unknown(default_dialog_state(lifecycle="active_client")),
            "dialog_state",
        )
        self.logger.info(
            "User memory reset after ticket closure",
            extra={"client_id": client_id},
        )

    async def _emit_ticket_closed_event(
        self,
        *,
        thread_id: str,
        manually_closed: bool,
        close_reason: str | None,
    ) -> None:
        thread = await self.thread_read.get_thread_with_project_view(thread_id)
        if not thread or not thread.project_id:
            return

        await self.event_emitter.emit_event(
            stream_id=thread_id,
            project_id=thread.project_id,
            event_type="ticket_closed",
            payload={
                "manually_closed": manually_closed,
                "reason": close_reason or "manager_closed",
            },
        )

    async def _emit_manager_claimed_event(
        self,
        *,
        thread_id: str,
        manager: ManagerActor,
    ) -> None:
        thread = await self.thread_read.get_thread_with_project_view(thread_id)
        if not thread or not thread.project_id:
            return

        manager_display_name = await self.resolve_manager_display_name(
            project_id=thread.project_id,
            manager_chat_id=manager.telegram_chat_id,
            manager_user_id=manager.user_id,
        )
        await self.event_emitter.emit_event(
            stream_id=thread_id,
            project_id=thread.project_id,
            event_type="manager_claimed",
            payload=build_manager_audit_payload(
                manager_user_id=manager.user_id,
                manager_chat_id=manager.telegram_chat_id,
                manager_display_name=manager_display_name,
            ),
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
        manager_display_name = await self.resolve_manager_display_name(
            project_id=project_id,
            manager_chat_id=manager_chat_id,
            manager_user_id=resolved_manager_user_id,
        )

        prefixed_text = await self._prefixed_manager_text(
            manager_display_name=manager_display_name,
            manager_text=manager_text,
        )

        await self.thread_messages.append_manager_reply_message(
            thread_id, prefixed_text
        )
        await self._send_reply_to_client(
            project_id=project_id,
            thread_id=thread_id,
            chat_id=str(thread_snapshot.chat_id)
            if thread_snapshot.chat_id is not None
            else None,
            text=prefixed_text,
        )
        await self._emit_manager_reply_event(
            thread_id=thread_id,
            project_id=project_id,
            manager_text=manager_text,
            manager_user_id=resolved_manager_user_id,
            manager_chat_id=manager_chat_id,
            manager_display_name=manager_display_name,
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
        return build_display_name(
            full_name=chat_data.get("title"),
            first_name=chat_data.get("first_name"),
            last_name=chat_data.get("last_name"),
            username=chat_data.get("username"),
            fallback="Менеджер",
        )

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
        thread_view = await self.thread_read.get_thread_with_project_view(thread_id)
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
        manager_display_name: str,
        manager_text: str,
    ) -> str:
        return f"[{manager_display_name}]: {manager_text}"

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
        self._ensure_telegram_response_ok(
            thread_id,
            response,
            payload={"chat_id": client_chat_id, "text_length": len(text)},
        )

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
        self,
        thread_id: str,
        response: dict[str, object],
        *,
        payload: dict[str, object],
    ) -> None:
        if response.get("ok") is not False:
            return

        self.logger.error(
            "Failed to send manager reply",
            extra={
                "thread_id": thread_id,
                "telegram_ok": response.get("ok"),
                "telegram_error_code": response.get("error_code"),
                "telegram_description": response.get("description"),
                "telegram_response": response,
                "payload": payload,
            },
        )
        raise InternalServiceError("Failed to deliver manager reply to client")

    async def _emit_manager_reply_event(
        self,
        *,
        thread_id: str,
        project_id: str,
        manager_text: str,
        manager_user_id: str,
        manager_chat_id: str | None,
        manager_display_name: str,
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
                    manager_display_name=manager_display_name,
                ),
            },
        )
