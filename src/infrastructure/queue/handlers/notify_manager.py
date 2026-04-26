"""Queue handler for manager notifications."""

from __future__ import annotations

from typing import Any, Awaitable, Callable, Mapping

import asyncpg

from src.domain.project_plane.manager_notifications import select_manager_notification_targets
from src.infrastructure.db.repositories.project import ProjectRepository
from src.infrastructure.db.repositories.thread_repository import ThreadRepository
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.queue.job_exceptions import PermanentJobError, TransientJobError
from src.infrastructure.queue.telegram_sender import TelegramSender
from src.utils.uuid_utils import ensure_uuid

logger = get_logger(__name__)

RedisGetter = Callable[[], Awaitable[Any]]


def _view_get(view: Any, key: str, default: Any = None) -> Any:
    if isinstance(view, Mapping):
        return view.get(key, default)
    return getattr(view, key, default)


async def get_client_display_name(pool: asyncpg.Pool, project_id: str, client_id: str) -> str:
    """Resolve a readable client name for notification text."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT username, full_name FROM clients WHERE id = $1 AND project_id = $2",
            ensure_uuid(client_id),
            ensure_uuid(project_id),
        )

    if row:
        if row["full_name"]:
            return row["full_name"]
        if row["username"]:
            return row["username"]
    return "Клиент"


def build_manager_reply_markup(*, thread_id: str, is_claimed: bool) -> dict[str, object]:
    buttons: list[list[dict[str, str]]] = []
    if not is_claimed:
        buttons.append([{"text": "✏️ Ответить", "callback_data": f"reply:{thread_id}"}])
    buttons.append([{"text": "✅ Закрыть тикет", "callback_data": f"close:{thread_id}"}])
    return {"inline_keyboard": buttons}


async def handle_notify_manager(
    job: Mapping[str, object],
    *,
    thread_repo: ThreadRepository,
    project_repo: ProjectRepository,
    telegram_sender: TelegramSender,
    redis_getter: RedisGetter,
    worker_id: str,
) -> bool:
    payload = job.get("payload") or {}
    if not isinstance(payload, Mapping):
        raise PermanentJobError("notify_manager payload must be an object")

    thread_id_raw = payload.get("thread_id")
    if not thread_id_raw:
        raise PermanentJobError("notify_manager job missing thread_id")

    thread_id = str(thread_id_raw)
    message = str(payload.get("message") or "")
    target_manager_chat_id = payload.get("target_manager_telegram_chat_id") or payload.get("manager_chat_id")
    target_manager_user_id = payload.get("manager_user_id")

    thread_info = await thread_repo.get_thread_with_project_view(thread_id)
    if not thread_info:
        logger.error("Thread not found", extra={"thread_id": thread_id, "job_id": job.get("id")})
        raise TransientJobError("Thread not found for notify_manager")

    project_id = _view_get(thread_info, "project_id")
    client_id = _view_get(thread_info, "client_id")

    if not project_id:
        raise PermanentJobError("Thread runtime view missing project_id")

    client_name = "Клиент"
    if client_id:
        client_name = await get_client_display_name(thread_repo.pool, str(project_id), str(client_id))

    project_settings = await project_repo.get_project_settings(str(project_id))
    manager_bot_token = _view_get(project_settings, "manager_bot_token")

    if not manager_bot_token:
        logger.error(
            "Manager bot token not set",
            extra={"project_id": project_id, "job_id": job.get("id")},
        )
        raise PermanentJobError("Manager bot token not set")

    manager_targets = await project_repo.get_manager_notification_recipients(str(project_id))
    manager_targets = select_manager_notification_targets(
        manager_targets,
        manager_user_id=str(target_manager_user_id) if target_manager_user_id else None,
        manager_chat_id=str(target_manager_chat_id) if target_manager_chat_id else None,
    )

    if not manager_targets:
        logger.warning(
            "No managers defined for project",
            extra={"project_id": project_id, "job_id": job.get("id")},
        )
        raise PermanentJobError("No manager notification targets")

    redis = await redis_getter()
    is_claimed = bool(await redis.exists(f"awaiting_reply_thread:{thread_id}"))
    reply_markup = build_manager_reply_markup(thread_id=thread_id, is_claimed=is_claimed)

    success_count = 0
    for target in manager_targets:
        result = await telegram_sender.send_message(
            bot_token=str(manager_bot_token),
            chat_id=target.telegram_chat_id,
            text=f"Новое сообщение от {client_name} (thread {thread_id}):\n\n{message}",
            reply_markup=reply_markup,
        )

        if result.ok:
            success_count += 1
            logger.info(
                "Manager notified",
                extra={
                    "job_id": job.get("id"),
                    "thread_id": thread_id,
                    "manager_user_id": target.user_id,
                    "manager_chat_id": target.telegram_chat_id,
                    "worker_id": worker_id,
                },
            )
        else:
            logger.error(
                "Manager notification failed",
                extra={
                    "job_id": job.get("id"),
                    "thread_id": thread_id,
                    "manager_user_id": target.user_id,
                    "manager_chat_id": target.telegram_chat_id,
                    "error": result.error,
                    "status_code": result.status_code,
                },
            )

    if success_count <= 0:
        raise TransientJobError("Telegram delivery failed for all manager targets")

    return True
