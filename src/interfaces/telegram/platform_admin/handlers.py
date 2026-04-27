"""
Platform control-plane Telegram command and callback handlers.
"""

from collections.abc import Awaitable, Callable
import json
import uuid

import httpx
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.application.services.platform_bot_service import PlatformBotService
from src.infrastructure.config.settings import settings
from src.infrastructure.db.repositories.project import ProjectRepository
from src.infrastructure.db.repositories.user_repository import UserRepository
from src.infrastructure.logging.logger import get_logger
from src.infrastructure.redis.client import get_redis_client
from src.interfaces.telegram.platform_admin.keyboards import (
    make_back_keyboard,
    make_main_menu_keyboard,
    make_project_dynamic_keyboard,
    make_projects_list_keyboard,
    make_token_help_keyboard,
)
from src.utils.uuid_utils import ensure_uuid

logger = get_logger(__name__)

AdminResponse = tuple[str, InlineKeyboardMarkup | None]
AdminStateHandler = Callable[[str, str, object], Awaitable[AdminResponse]]

STATE_PREFIX = "admin_state:"
DATA_PREFIX = "admin_data:"

STATE_IDLE = "idle"
STATE_AWAIT_PROJECT_NAME = "await_project_name"
STATE_AWAIT_CLIENT_TOKEN = "await_client_token"
STATE_AWAIT_MANAGER_TOKEN = "await_manager_token"
STATE_AWAIT_ADD_MANAGER = "await_add_manager"
STATE_DELETE_AWAIT_CONFIRM = "delete:await_confirm"
STATE_AWAIT_DETACH_CHOICE = "await_detach_choice"
STATE_AWAIT_KNOWLEDGE_FILE = "await_knowledge_file"


async def _get_state(chat_id: str) -> str:
    redis = await get_redis_client()
    state = await redis.get(f"{STATE_PREFIX}{chat_id}")
    return (
        state.decode() if state and isinstance(state, bytes) else (state or STATE_IDLE)
    )


async def _set_state(chat_id: str, state: str):
    redis = await get_redis_client()
    await redis.setex(f"{STATE_PREFIX}{chat_id}", 600, state)
    logger.debug("State set", extra={"chat_id": chat_id, "state": state})


async def _clear_state(chat_id: str):
    redis = await get_redis_client()
    await redis.delete(f"{STATE_PREFIX}{chat_id}")
    await redis.delete(f"{DATA_PREFIX}{chat_id}")
    logger.debug("State cleared", extra={"chat_id": chat_id})


async def _get_data(chat_id: str) -> dict[str, object]:
    redis = await get_redis_client()
    data = await redis.get(f"{DATA_PREFIX}{chat_id}")
    if data:
        if isinstance(data, bytes):
            data = data.decode()
        return json.loads(data)
    return {}


async def _set_data(chat_id: str, data: dict[str, object]):
    redis = await get_redis_client()
    await redis.setex(f"{DATA_PREFIX}{chat_id}", 600, json.dumps(data))
    logger.debug(
        "Data stored", extra={"chat_id": chat_id, "data_keys": list(data.keys())}
    )


async def handle_admin_command(text: str, pool) -> AdminResponse:
    parts = text.strip().split()
    if not parts:
        return "Пустая команда.", None

    cmd = parts[0].lower()
    logger.info("Admin command received", extra={"cmd": cmd, "args": parts[1:]})

    if cmd == "/start":
        return await _cmd_start()
    if cmd == "/help":
        return _cmd_help(), None
    return await _process_admin_step(text, None, pool, None, None)


async def _cmd_start() -> AdminResponse:
    return "Добро пожаловать в админ-панель фабрики ботов!", make_main_menu_keyboard()


def _cmd_help() -> str:
    return "**Справка**\n/start - Главное меню\nИспользуйте кнопки для управления."


async def handle_admin_step(chat_id: str, text: str, pool) -> AdminResponse | None:
    state = await _get_state(chat_id)
    if state == STATE_IDLE:
        return None
    data = await _get_data(chat_id)
    return await _process_admin_step(text, data, pool, chat_id, state)


async def _process_admin_step(
    text: str,
    data: dict[str, object],
    pool,
    chat_id: str | None = None,
    state: str | None = None,
) -> AdminResponse:
    del data

    if chat_id is None or state is None:
        return "Ошибка состояния. Напишите /start.", None

    logger.debug(
        "Processing step", extra={"chat_id": chat_id, "state": state, "text": text[:30]}
    )

    if text.strip() == "/start":
        await _clear_state(chat_id)
        return await _cmd_start()

    handler = _admin_step_handlers().get(state)
    if handler is None:
        return await _reset_unknown_admin_step(chat_id)

    return await handler(chat_id, text, pool)


def _admin_step_handlers() -> dict[str, AdminStateHandler]:
    return {
        STATE_AWAIT_PROJECT_NAME: _step_await_project_name,
        STATE_AWAIT_CLIENT_TOKEN: _step_await_client_token,
        STATE_AWAIT_MANAGER_TOKEN: _step_await_manager_token,
        STATE_AWAIT_ADD_MANAGER: _step_await_add_manager,
        STATE_DELETE_AWAIT_CONFIRM: _step_delete_confirm,
        STATE_AWAIT_DETACH_CHOICE: _step_detach_choice,
        STATE_AWAIT_KNOWLEDGE_FILE: _step_await_knowledge_file,
    }


async def _reset_unknown_admin_step(chat_id: str) -> AdminResponse:
    await _clear_state(chat_id)
    return "Диалог сброшен. Напишите /start.", None


async def _step_await_project_name(chat_id: str, name: str, pool) -> AdminResponse:
    service = PlatformBotService(pool)
    projects = (await service.list_projects_for_telegram_user(int(chat_id))).projects
    if any(
        project.name == name
        for project in projects
        if str(project.id) != str(settings.ADMIN_PROJECT_ID)
    ):
        return "У вас уже есть проект с таким именем. Придумайте другое.", None

    project_id = await service.create_project_for_telegram_user(int(chat_id), name)
    await _clear_state(chat_id)
    return await _show_project_menu(chat_id, project_id, pool)


async def _step_await_client_token(chat_id: str, token: str, pool) -> AdminResponse:
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    if not project_id:
        await _clear_state(chat_id)
        return "Ошибка: проект не указан.", None

    username = await _verify_token(token)
    if not username:
        return "Неверный токен. Попробуйте еще раз.", make_token_help_keyboard()

    await _set_project_token(project_id, token, pool)
    await _clear_state(chat_id)
    return await _show_project_menu(chat_id, project_id, pool)


async def _step_await_manager_token(chat_id: str, token: str, pool) -> AdminResponse:
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    if not project_id:
        await _clear_state(chat_id)
        return "Ошибка: проект не указан.", None

    username = await _verify_token(token)
    if not username:
        return "Неверный токен. Попробуйте еще раз.", make_token_help_keyboard()

    await _set_manager_token(project_id, token, chat_id, pool)
    await _clear_state(chat_id)

    text = (
        f"Менеджерский бот создан: @{username}\n\n"
        "Чтобы добавить других менеджеров, нажмите кнопку 'Менеджеры'."
    )
    return text, await _get_project_menu_keyboard(project_id, pool)


async def _step_await_add_manager(chat_id: str, manager_id: str, pool) -> AdminResponse:
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    if not project_id:
        await _clear_state(chat_id)
        return "Ошибка: проект не указан.", None

    if not manager_id.strip().lstrip("-").isdigit():
        return "ChatID должен быть числом. Попробуйте еще раз.", None

    try:
        success_text = await PlatformBotService(pool).add_manager_by_chat_id(
            project_id, manager_id
        )
    except Exception as exc:
        logger.exception(
            "Failed to add manager",
            extra={
                "chat_id": chat_id,
                "project_id": project_id,
                "manager_id": manager_id,
                "error": str(exc),
                "error_type": type(exc).__name__,
                "policy": "safe_user_fallback",
            },
        )
        return "Ошибка при добавлении менеджера. Попробуйте позже.", None

    await _clear_state(chat_id)
    return success_text, await _get_project_menu_keyboard(project_id, pool)


async def _step_delete_confirm(chat_id: str, text: str, pool) -> AdminResponse:
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    project_name = data.get("project_name")

    if not project_id:
        await _clear_state(chat_id)
        return "Ошибка: проект не найден.", None

    if text.strip().lower() == "да":
        try:
            async with pool.acquire() as conn:
                await conn.execute(
                    "DELETE FROM projects WHERE id = $1", ensure_uuid(project_id)
                )
            logger.info(
                "Project deleted",
                extra={"project_id": project_id, "name": project_name},
            )
            await _clear_state(chat_id)
            return f"Проект «{project_name}» ({project_id}) успешно удален.", None
        except Exception as exc:
            logger.exception(
                "Failed to delete project",
                extra={
                    "chat_id": chat_id,
                    "project_id": project_id,
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "policy": "safe_user_fallback",
                },
            )
            await _clear_state(chat_id)
            return "Ошибка при удалении проекта. Попробуйте позже.", None

    await _clear_state(chat_id)
    return "Удаление отменено.", None


async def _step_detach_choice(chat_id: str, choice: str, pool) -> AdminResponse:
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    if not project_id:
        await _clear_state(chat_id)
        return "Ошибка: проект не указан.", None

    project_repo = ProjectRepository(pool)
    if choice == "client":
        await project_repo.set_bot_token(project_id, None)
        await project_repo.upsert_project_channel(
            project_id,
            kind="client",
            provider="telegram",
            status="disabled",
            config_json={"token_configured": False},
        )
        await _clear_state(chat_id)
        return "Клиентский бот откреплен.", await _get_project_menu_keyboard(
            project_id, pool
        )
    if choice == "manager":
        await project_repo.set_manager_bot_token(project_id, None)
        await project_repo.upsert_project_channel(
            project_id,
            kind="manager",
            provider="telegram",
            status="disabled",
            config_json={"token_configured": False},
        )
        await _clear_state(chat_id)
        return "Менеджерский бот откреплен.", await _get_project_menu_keyboard(
            project_id, pool
        )

    await _clear_state(chat_id)
    return "Отмена.", await _get_project_menu_keyboard(project_id, pool)


async def _step_await_knowledge_file(chat_id: str, text: str, pool) -> AdminResponse:
    return (
        "Ожидаю файл со знаниями, а не текст. Отправьте PDF, DOCX или TXT.",
        make_back_keyboard(),
    )


def _callback_project_id(callback_data: str) -> str:
    return callback_data.split(":", 1)[1]


async def _handle_new_project_callback(chat_id: str, pool) -> AdminResponse:
    await _set_state(chat_id, STATE_AWAIT_PROJECT_NAME)
    return (
        "Введите название нового проекта (например: Идея на миллион):",
        make_back_keyboard(),
    )


async def _handle_list_projects_callback(chat_id: str, pool) -> AdminResponse:
    return await _show_projects_list(chat_id, pool)


async def _handle_project_callback(
    callback_data: str, chat_id: str, pool
) -> AdminResponse:
    return await _show_project_menu(chat_id, _callback_project_id(callback_data), pool)


async def _handle_create_client_bot_callback(
    callback_data: str, chat_id: str, pool
) -> AdminResponse:
    project_id = _callback_project_id(callback_data)
    await _set_data(chat_id, {"project_id": project_id})
    await _set_state(chat_id, STATE_AWAIT_CLIENT_TOKEN)
    return (
        "Отправьте токен клиентского бота следующим сообщением.\n\n"
        "Как получить токен: @BotFather -> /newbot",
        make_token_help_keyboard(),
    )


async def _handle_create_manager_bot_callback(
    callback_data: str, chat_id: str, pool
) -> AdminResponse:
    project_id = _callback_project_id(callback_data)
    await _set_data(chat_id, {"project_id": project_id})
    await _set_state(chat_id, STATE_AWAIT_MANAGER_TOKEN)
    return (
        "Отправьте токен менеджерского бота следующим сообщением.\n\n"
        "Как получить токен: @BotFather -> /newbot",
        make_token_help_keyboard(),
    )


async def _handle_knowledge_callback(
    callback_data: str, chat_id: str, pool
) -> AdminResponse:
    project_id = _callback_project_id(callback_data)
    await _set_data(chat_id, {"project_id": project_id})
    await _set_state(chat_id, STATE_AWAIT_KNOWLEDGE_FILE)
    return (
        "Отправьте файл с документами (PDF, DOCX, TXT).\n"
        "Я обработаю его и добавлю в базу знаний проекта.",
        make_back_keyboard(f"project:{project_id}"),
    )


def _format_project_team_lines(manager_members, legacy_targets) -> str:
    lines = ["Команда проекта:"]
    member_telegram_ids = set()

    for member in manager_members:
        label = member.username or member.full_name or member.email or member.user_id
        telegram_id = member.telegram_id
        if telegram_id is not None:
            member_telegram_ids.add(str(telegram_id))
        telegram_suffix = f" · tg `{telegram_id}`" if telegram_id is not None else ""
        lines.append(f"- `{member.role}` - {label}{telegram_suffix}")

    for legacy_target in legacy_targets:
        if str(legacy_target) not in member_telegram_ids:
            lines.append(f"- `legacy-manager` - tg `{legacy_target}`")

    return "\n".join(lines) + "\n\nВведите ChatID нового менеджера:"


async def _handle_managers_callback(
    callback_data: str, chat_id: str, pool
) -> AdminResponse:
    project_id = _callback_project_id(callback_data)
    team = await PlatformBotService(pool).get_project_team(project_id)

    if team.members or team.legacy_targets:
        text = _format_project_team_lines(team.members, team.legacy_targets)
    else:
        text = "В проекте пока нет менеджеров.\n\nВведите ChatID первого менеджера:"

    await _set_data(chat_id, {"project_id": project_id})
    await _set_state(chat_id, STATE_AWAIT_ADD_MANAGER)
    return text, make_back_keyboard(f"project:{project_id}")


async def _handle_detach_bot_callback(
    callback_data: str, chat_id: str, pool
) -> AdminResponse:
    project_id = _callback_project_id(callback_data)
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "Клиентского", callback_data=f"detach_client:{project_id}"
                )
            ],
            [
                InlineKeyboardButton(
                    "Менеджерского", callback_data=f"detach_manager:{project_id}"
                )
            ],
            [InlineKeyboardButton("Назад", callback_data=f"project:{project_id}")],
        ]
    )
    return "Какого бота открепить?", keyboard


async def _detach_project_bot(project_id: str, pool, *, kind: str) -> AdminResponse:
    project_repo = ProjectRepository(pool)

    if kind == "client":
        await project_repo.set_bot_token(project_id, None)
        message = "Клиентский бот откреплен."
    else:
        await project_repo.set_manager_bot_token(project_id, None)
        message = "Менеджерский бот откреплен."

    await project_repo.upsert_project_channel(
        project_id,
        kind=kind,
        provider="telegram",
        status="disabled",
        config_json={"token_configured": False},
    )
    return message, await _get_project_menu_keyboard(project_id, pool)


async def _handle_detach_client_callback(
    callback_data: str, chat_id: str, pool
) -> AdminResponse:
    return await _detach_project_bot(
        _callback_project_id(callback_data), pool, kind="client"
    )


async def _handle_detach_manager_callback(
    callback_data: str, chat_id: str, pool
) -> AdminResponse:
    return await _detach_project_bot(
        _callback_project_id(callback_data), pool, kind="manager"
    )


async def _handle_delete_callback(
    callback_data: str, chat_id: str, pool
) -> AdminResponse:
    project_id = _callback_project_id(callback_data)

    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT name FROM projects WHERE id = $1", ensure_uuid(project_id)
        )
        if not row:
            return "Проект не найден.", None
        project_name = row["name"]

    await _set_data(chat_id, {"project_id": project_id, "project_name": project_name})
    await _set_state(chat_id, STATE_DELETE_AWAIT_CONFIRM)

    text = (
        f"Вы уверены, что хотите удалить проект?\n\n"
        f"Название: {project_name}\n"
        f"ID: `{project_id}`\n\n"
        f"Это действие необратимо. Все данные будут удалены.\n\n"
        f"Для подтверждения введите слово `да`."
    )
    return text, make_back_keyboard(f"project:{project_id}")


async def _handle_back_to_main_callback(chat_id: str, pool) -> AdminResponse:
    await _clear_state(chat_id)
    return await _cmd_start()


async def _handle_back_to_project_callback(
    callback_data: str, chat_id: str, pool
) -> AdminResponse:
    project_id = _callback_project_id(callback_data)
    await _clear_state(chat_id)
    return await _show_project_menu(chat_id, project_id, pool)


PREFIX_CALLBACK_HANDLERS = (
    ("project:", _handle_project_callback),
    ("create_client_bot:", _handle_create_client_bot_callback),
    ("create_manager_bot:", _handle_create_manager_bot_callback),
    ("knowledge:", _handle_knowledge_callback),
    ("managers:", _handle_managers_callback),
    ("detach_bot:", _handle_detach_bot_callback),
    ("detach_client:", _handle_detach_client_callback),
    ("detach_manager:", _handle_detach_manager_callback),
    ("delete:", _handle_delete_callback),
    ("back_to_project:", _handle_back_to_project_callback),
)


async def handle_admin_callback(
    callback_data: str, chat_id: str, pool
) -> AdminResponse:
    logger.info("Callback", extra={"data": callback_data, "chat_id": chat_id})

    if callback_data == "newproject":
        return await _handle_new_project_callback(chat_id, pool)

    if callback_data == "listprojects":
        return await _handle_list_projects_callback(chat_id, pool)

    if callback_data == "back_to_main":
        return await _handle_back_to_main_callback(chat_id, pool)

    for prefix, handler in PREFIX_CALLBACK_HANDLERS:
        if callback_data.startswith(prefix):
            return await handler(callback_data, chat_id, pool)

    return "Неизвестная кнопка.", None


async def _verify_token(token: str) -> str | None:
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"https://api.telegram.org/bot{token}/getMe", timeout=10
            )
            if resp.status_code == 200 and resp.json().get("ok"):
                return resp.json()["result"]["username"]
        except httpx.HTTPError as exc:
            logger.warning(
                "Telegram token verification request failed",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "policy": "return_invalid_token",
                },
            )
            return None
    return None


async def _set_project_token(project_id: str, token: str, pool) -> None:
    secret_token = uuid.uuid4().hex
    project_repo = ProjectRepository(pool)
    await project_repo.set_bot_token(project_id, token)
    await project_repo.set_webhook_secret(project_id, secret_token)

    base_url = settings.RENDER_EXTERNAL_URL or settings.PUBLIC_URL
    if not base_url:
        raise ValueError("PUBLIC_URL not set")

    webhook_url = f"{base_url.rstrip('/')}/webhooks/projects/{project_id}/client"
    await project_repo.upsert_project_channel(
        project_id,
        kind="client",
        provider="telegram",
        status="active",
        config_json={"webhook_url": webhook_url, "token_configured": True},
    )
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": webhook_url, "secret_token": secret_token},
        )
        if resp.status_code != 200 or not resp.json().get("ok"):
            raise Exception(f"Webhook setup failed: {resp.text}")


async def _set_manager_token(
    project_id: str, token: str, admin_chat_id: str, pool
) -> None:
    project_repo = ProjectRepository(pool)
    await project_repo.set_manager_bot_token(project_id, token)
    user_repo = UserRepository(pool)
    admin_user_id, _ = await user_repo.get_or_create_by_telegram(
        int(admin_chat_id), first_name="", username=None
    )
    await project_repo.add_project_member(project_id, admin_user_id, "owner")

    manager_secret = uuid.uuid4().hex
    await project_repo.set_manager_webhook_secret(project_id, manager_secret)

    base_url = settings.RENDER_EXTERNAL_URL or settings.PUBLIC_URL
    if not base_url:
        raise ValueError("PUBLIC_URL not set")

    webhook_url = f"{base_url.rstrip('/')}/webhooks/projects/{project_id}/manager"
    await project_repo.upsert_project_channel(
        project_id,
        kind="manager",
        provider="telegram",
        status="active",
        config_json={"webhook_url": webhook_url, "token_configured": True},
    )
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": webhook_url, "secret_token": manager_secret},
        )
        if resp.status_code != 200 or not resp.json().get("ok"):
            raise Exception(f"Manager webhook setup failed: {resp.text}")


async def _get_bot_username(token: str) -> str | None:
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(
                f"https://api.telegram.org/bot{token}/getMe", timeout=5
            )
            if resp.status_code == 200 and resp.json().get("ok"):
                return resp.json()["result"]["username"]
        except httpx.HTTPError as exc:
            logger.warning(
                "Telegram bot username lookup failed",
                extra={
                    "error": str(exc),
                    "error_type": type(exc).__name__,
                    "policy": "return_missing_username",
                },
            )
            return None
    return None


async def _show_projects_list(chat_id: str, pool) -> AdminResponse:
    rows = [
        {"id": project.id, "name": project.name}
        for project in (
            await PlatformBotService(pool).list_projects_for_telegram_user(int(chat_id))
        ).projects
        if str(project.id) != str(settings.ADMIN_PROJECT_ID)
    ]

    if not rows:
        text = "У вас пока нет проектов. Создайте первый."
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Новый проект", callback_data="newproject")]]
        )
        return text, keyboard

    projects = [(str(row["id"]), row["name"]) for row in rows]
    return "Ваши проекты:", make_projects_list_keyboard(projects)


async def _show_project_menu(chat_id: str, project_id: str, pool) -> AdminResponse:
    del chat_id

    project_name = await _project_name(project_id, pool)
    if project_name is None:
        return "Проект не найден.", None

    settings_view = await ProjectRepository(pool).get_project_settings(project_id)
    has_client = bool(settings_view.bot_token)
    has_manager = bool(settings_view.manager_bot_token)

    text = await _project_menu_text(
        project_name=project_name,
        client_token=settings_view.bot_token,
        manager_token=settings_view.manager_bot_token,
    )
    keyboard = make_project_dynamic_keyboard(project_id, has_client, has_manager)
    return text, keyboard


async def _project_name(project_id: str, pool) -> str | None:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT name FROM projects WHERE id = $1", ensure_uuid(project_id)
        )
    return str(row["name"]) if row else None


async def _project_menu_text(
    *,
    project_name: str,
    client_token: str | None,
    manager_token: str | None,
) -> str:
    lines = [
        f"Проект: {project_name}",
        _project_setup_status(client_token=client_token, manager_token=manager_token),
    ]

    await _append_bot_status_line(lines, label="Клиентский бот", token=client_token)
    await _append_bot_status_line(lines, label="Менеджерский бот", token=manager_token)

    return "\n".join(lines)


def _project_setup_status(
    *, client_token: str | None, manager_token: str | None
) -> str:
    if client_token and manager_token:
        return "Проект настроен полностью."
    return "Проект настроен не полностью."


async def _append_bot_status_line(
    lines: list[str], *, label: str, token: str | None
) -> None:
    if not token:
        return

    username = await _get_bot_username(token)
    if username:
        lines.append(f"{label}: @{username}")
        return

    lines.append(f"{label}: токен установлен")


async def _get_project_menu_keyboard(project_id: str, pool) -> InlineKeyboardMarkup:
    project_repo = ProjectRepository(pool)
    settings_view = await project_repo.get_project_settings(project_id)
    has_client = bool(settings_view.bot_token)
    has_manager = bool(settings_view.manager_bot_token)
    return make_project_dynamic_keyboard(project_id, has_client, has_manager)
