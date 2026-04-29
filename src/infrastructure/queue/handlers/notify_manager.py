"""Queue handler for manager notifications."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable, Mapping, Protocol

import asyncpg

from src.application.ports.project_port import ProjectNotificationPort
from src.domain.display_names import build_display_name
from src.application.ports.thread_port import ThreadReadPort
from src.domain.project_plane.manager_notifications import (
    ManagerNotificationTarget,
    select_manager_notification_targets,
)
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.queue.job_exceptions import PermanentJobError, TransientJobError
from src.infrastructure.queue.telegram_sender import TelegramSender
from src.utils.uuid_utils import ensure_uuid

logger = get_logger(__name__)


class RedisExistsPort(Protocol):
    async def exists(self, key: str) -> object: ...


RedisGetter = Callable[[], Awaitable[RedisExistsPort]]


@dataclass(frozen=True)
class NotifyManagerPayload:
    thread_id: str
    message: str
    target_manager_chat_id: str | None
    target_manager_user_id: str | None


@dataclass(frozen=True)
class NotifyThreadContext:
    project_id: str
    client_id: str | None
    client_name: str


def _view_get(view: object, key: str, default: object = None) -> object:
    if isinstance(view, Mapping):
        return view.get(key, default)
    return getattr(view, key, default)


def _job_id(job: Mapping[str, object]) -> object:
    return job.get("id")


def _parse_payload(job: Mapping[str, object]) -> NotifyManagerPayload:
    payload = job.get("payload") or {}
    if not isinstance(payload, Mapping):
        raise PermanentJobError("notify_manager payload must be an object")

    thread_id_raw = payload.get("thread_id")
    if not thread_id_raw:
        raise PermanentJobError("notify_manager job missing thread_id")

    target_chat_id = payload.get("target_manager_telegram_chat_id") or payload.get(
        "manager_chat_id"
    )
    target_user_id = payload.get("manager_user_id")

    return NotifyManagerPayload(
        thread_id=str(thread_id_raw),
        message=str(payload.get("message") or ""),
        target_manager_chat_id=str(target_chat_id) if target_chat_id else None,
        target_manager_user_id=str(target_user_id) if target_user_id else None,
    )


async def get_client_display_name(
    pool: asyncpg.Pool, project_id: str, client_id: str
) -> str:
    """Resolve a readable client name for notification text."""
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            """
            SELECT username, full_name, email
            FROM clients
            WHERE id = $1 AND project_id = $2
            """,
            ensure_uuid(client_id),
            ensure_uuid(project_id),
        )

    if not row:
        return "Клиент"

    return build_display_name(
        full_name=row["full_name"],
        username=row["username"],
        email=row["email"],
        fallback="Клиент",
    )


async def _load_thread_context(
    *,
    thread_id: str,
    job: Mapping[str, object],
    thread_read_repo: ThreadReadPort,
    db_pool: asyncpg.Pool,
) -> NotifyThreadContext:
    thread_info = await thread_read_repo.get_thread_with_project_view(thread_id)
    if not thread_info:
        logger.error(
            "Thread not found", extra={"thread_id": thread_id, "job_id": _job_id(job)}
        )
        raise TransientJobError("Thread not found for notify_manager")

    project_id = _view_get(thread_info, "project_id")
    client_id = _view_get(thread_info, "client_id")

    if not project_id:
        raise PermanentJobError("Thread runtime view missing project_id")

    client_name = "Клиент"
    if client_id:
        client_name = await get_client_display_name(
            db_pool, str(project_id), str(client_id)
        )

    return NotifyThreadContext(
        project_id=str(project_id),
        client_id=str(client_id) if client_id else None,
        client_name=client_name,
    )


async def _load_manager_bot_token(
    *,
    project_id: str,
    job: Mapping[str, object],
    project_repo: ProjectNotificationPort,
) -> str:
    project_settings = await project_repo.get_project_settings(project_id)
    manager_bot_token = _view_get(project_settings, "manager_bot_token")

    if not manager_bot_token:
        logger.error(
            "Manager bot token not set",
            extra={"project_id": project_id, "job_id": _job_id(job)},
        )
        raise PermanentJobError("Manager bot token not set")

    return str(manager_bot_token)


async def _load_manager_targets(
    *,
    project_id: str,
    payload: NotifyManagerPayload,
    job: Mapping[str, object],
    project_repo: ProjectNotificationPort,
) -> list[ManagerNotificationTarget]:
    manager_targets = await project_repo.get_manager_notification_recipients(project_id)
    selected_targets = select_manager_notification_targets(
        manager_targets,
        manager_user_id=payload.target_manager_user_id,
        manager_chat_id=payload.target_manager_chat_id,
    )

    if not selected_targets:
        logger.warning(
            "No managers defined for project",
            extra={"project_id": project_id, "job_id": _job_id(job)},
        )
        raise PermanentJobError("No manager notification targets")

    return selected_targets


def build_manager_reply_markup(
    *, thread_id: str, is_claimed: bool
) -> dict[str, object]:
    buttons: list[list[dict[str, str]]] = []
    if not is_claimed:
        buttons.append([{"text": "✏️ Ответить", "callback_data": f"reply:{thread_id}"}])
    buttons.append(
        [{"text": "✅ Закрыть тикет", "callback_data": f"close:{thread_id}"}]
    )
    return {"inline_keyboard": buttons}


async def _build_reply_markup(
    *, thread_id: str, redis_getter: RedisGetter
) -> dict[str, object]:
    redis = await redis_getter()
    is_claimed = bool(await redis.exists(f"awaiting_reply_thread:{thread_id}"))
    return build_manager_reply_markup(thread_id=thread_id, is_claimed=is_claimed)


def _notification_text(*, client_name: str, thread_id: str, message: str) -> str:
    return f"Новое сообщение от {client_name} (thread {thread_id}):\n\n{message}"


def _log_delivery_success(
    *,
    job: Mapping[str, object],
    thread_id: str,
    target: ManagerNotificationTarget,
    worker_id: str,
) -> None:
    logger.info(
        "Manager notified",
        extra={
            "job_id": _job_id(job),
            "thread_id": thread_id,
            "manager_user_id": target.user_id,
            "manager_chat_id": target.telegram_chat_id,
            "worker_id": worker_id,
        },
    )


def _log_delivery_failure(
    *,
    job: Mapping[str, object],
    thread_id: str,
    target: ManagerNotificationTarget,
    error: object,
    status_code: object,
) -> None:
    logger.error(
        "Manager notification failed",
        extra={
            "job_id": _job_id(job),
            "thread_id": thread_id,
            "manager_user_id": target.user_id,
            "manager_chat_id": target.telegram_chat_id,
            "error": error,
            "status_code": status_code,
        },
    )


async def _send_manager_notifications(
    *,
    bot_token: str,
    targets: list[ManagerNotificationTarget],
    payload: NotifyManagerPayload,
    thread_context: NotifyThreadContext,
    reply_markup: dict[str, object],
    telegram_sender: TelegramSender,
    job: Mapping[str, object],
    worker_id: str,
) -> int:
    success_count = 0
    text = _notification_text(
        client_name=thread_context.client_name,
        thread_id=payload.thread_id,
        message=payload.message,
    )

    for target in targets:
        result = await telegram_sender.send_message(
            bot_token=bot_token,
            chat_id=target.telegram_chat_id,
            text=text,
            reply_markup=reply_markup,
        )

        if result.ok:
            success_count += 1
            _log_delivery_success(
                job=job,
                thread_id=payload.thread_id,
                target=target,
                worker_id=worker_id,
            )
        else:
            _log_delivery_failure(
                job=job,
                thread_id=payload.thread_id,
                target=target,
                error=result.error,
                status_code=result.status_code,
            )

    return success_count


def _ensure_any_delivery_succeeded(success_count: int) -> None:
    if success_count <= 0:
        raise TransientJobError("Telegram delivery failed for all manager targets")


async def handle_notify_manager(
    job: Mapping[str, object],
    *,
    thread_read_repo: ThreadReadPort,
    db_pool: asyncpg.Pool,
    project_repo: ProjectNotificationPort,
    telegram_sender: TelegramSender,
    redis_getter: RedisGetter,
    worker_id: str,
) -> bool:
    payload = _parse_payload(job)
    thread_context = await _load_thread_context(
        thread_id=payload.thread_id,
        job=job,
        thread_read_repo=thread_read_repo,
        db_pool=db_pool,
    )
    bot_token = await _load_manager_bot_token(
        project_id=thread_context.project_id,
        job=job,
        project_repo=project_repo,
    )
    targets = await _load_manager_targets(
        project_id=thread_context.project_id,
        payload=payload,
        job=job,
        project_repo=project_repo,
    )
    reply_markup = await _build_reply_markup(
        thread_id=payload.thread_id,
        redis_getter=redis_getter,
    )
    success_count = await _send_manager_notifications(
        bot_token=bot_token,
        targets=targets,
        payload=payload,
        thread_context=thread_context,
        reply_markup=reply_markup,
        telegram_sender=telegram_sender,
        job=job,
        worker_id=worker_id,
    )
    _ensure_any_delivery_succeeded(success_count)
    return True
