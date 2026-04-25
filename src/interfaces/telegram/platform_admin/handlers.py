"""
Platform control-plane Telegram command and callback handlers.
"""

from typing import Any, Dict, Optional, Tuple
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

AdminResponse = Tuple[str, Optional[InlineKeyboardMarkup]]

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
    return state.decode() if state and isinstance(state, bytes) else (state or STATE_IDLE)


async def _set_state(chat_id: str, state: str):
    redis = await get_redis_client()
    await redis.setex(f"{STATE_PREFIX}{chat_id}", 600, state)
    logger.debug("State set", extra={"chat_id": chat_id, "state": state})


async def _clear_state(chat_id: str):
    redis = await get_redis_client()
    await redis.delete(f"{STATE_PREFIX}{chat_id}")
    await redis.delete(f"{DATA_PREFIX}{chat_id}")
    logger.debug("State cleared", extra={"chat_id": chat_id})


async def _get_data(chat_id: str) -> Dict[str, Any]:
    redis = await get_redis_client()
    data = await redis.get(f"{DATA_PREFIX}{chat_id}")
    if data:
        if isinstance(data, bytes):
            data = data.decode()
        return json.loads(data)
    return {}


async def _set_data(chat_id: str, data: Dict[str, Any]):
    redis = await get_redis_client()
    await redis.setex(f"{DATA_PREFIX}{chat_id}", 600, json.dumps(data))
    logger.debug("Data stored", extra={"chat_id": chat_id, "data_keys": list(data.keys())})


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
    return (
        "**Справка**\n"
        "/start - Главное меню\n"
        "Используйте кнопки для управления."
    )


async def handle_admin_step(chat_id: str, text: str, pool) -> Optional[AdminResponse]:
    state = await _get_state(chat_id)
    if state == STATE_IDLE:
        return None
    data = await _get_data(chat_id)
    return await _process_admin_step(text, data, pool, chat_id, state)


async def _process_admin_step(
    text: str,
    data: Dict[str, Any],
    pool,
    chat_id: Optional[str] = None,
    state: Optional[str] = None,
) -> AdminResponse:
    if chat_id is None or state is None:
        return "Ошибка состояния. Напишите /start.", None

    logger.debug("Processing step", extra={"chat_id": chat_id, "state": state, "text": text[:30]})

    if text.strip() == "/start":
        await _clear_state(chat_id)
        return await _cmd_start()

    if state == STATE_AWAIT_PROJECT_NAME:
        return await _step_await_project_name(chat_id, text, pool)
    if state == STATE_AWAIT_CLIENT_TOKEN:
        return await _step_await_client_token(chat_id, text, pool)
    if state == STATE_AWAIT_MANAGER_TOKEN:
        return await _step_await_manager_token(chat_id, text, pool)
    if state == STATE_AWAIT_ADD_MANAGER:
        return await _step_await_add_manager(chat_id, text, pool)
    if state == STATE_DELETE_AWAIT_CONFIRM:
        return await _step_delete_confirm(chat_id, text, pool)
    if state == STATE_AWAIT_DETACH_CHOICE:
        return await _step_detach_choice(chat_id, text, pool)
    if state == STATE_AWAIT_KNOWLEDGE_FILE:
        return await _step_await_knowledge_file(chat_id, text, pool)

    await _clear_state(chat_id)
    return "Диалог сброшен. Напишите /start.", None


async def _step_await_project_name(chat_id: str, name: str, pool) -> AdminResponse:
    service = PlatformBotService(pool)
    projects = (await service.list_projects_for_telegram_user(int(chat_id))).projects
    if any(project.name == name for project in projects if str(project.id) != str(settings.ADMIN_PROJECT_ID)):
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
        success_text = await PlatformBotService(pool).add_manager_by_chat_id(project_id, manager_id)
    except Exception as exc:
        logger.exception("Failed to add manager", extra={"error": str(exc)})
        return f"Ошибка: {str(exc)}", None

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
                await conn.execute("DELETE FROM projects WHERE id = $1", ensure_uuid(project_id))
            logger.info("Project deleted", extra={"project_id": project_id, "name": project_name})
            await _clear_state(chat_id)
            return f"Проект «{project_name}» ({project_id}) успешно удален.", None
        except Exception as exc:
            logger.error("Failed to delete project", extra={"error": str(exc)})
            await _clear_state(chat_id)
            return f"Ошибка при удалении: {str(exc)}", None

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
        await project_repo.upsert_project_channel(project_id, kind="client", provider="telegram", status="disabled", config_json={"token_configured": False})
        await _clear_state(chat_id)
        return "Клиентский бот откреплен.", await _get_project_menu_keyboard(project_id, pool)
    if choice == "manager":
        await project_repo.set_manager_bot_token(project_id, None)
        await project_repo.upsert_project_channel(project_id, kind="manager", provider="telegram", status="disabled", config_json={"token_configured": False})
        await _clear_state(chat_id)
        return "Менеджерский бот откреплен.", await _get_project_menu_keyboard(project_id, pool)

    await _clear_state(chat_id)
    return "Отмена.", await _get_project_menu_keyboard(project_id, pool)


async def _step_await_knowledge_file(chat_id: str, text: str, pool) -> AdminResponse:
    return "Ожидаю файл со знаниями, а не текст. Отправьте PDF, DOCX или TXT.", make_back_keyboard()


async def handle_admin_callback(callback_data: str, chat_id: str, pool) -> AdminResponse:
    logger.info("Callback", extra={"data": callback_data, "chat_id": chat_id})

    if callback_data == "newproject":
        await _set_state(chat_id, STATE_AWAIT_PROJECT_NAME)
        return "Введите название нового проекта (например: Идея на миллион):", make_back_keyboard()

    if callback_data == "listprojects":
        return await _show_projects_list(chat_id, pool)

    if callback_data.startswith("project:"):
        project_id = callback_data.split(":", 1)[1]
        return await _show_project_menu(chat_id, project_id, pool)

    if callback_data.startswith("create_client_bot:"):
        project_id = callback_data.split(":", 1)[1]
        await _set_data(chat_id, {"project_id": project_id})
        await _set_state(chat_id, STATE_AWAIT_CLIENT_TOKEN)
        return (
            "Отправьте токен клиентского бота следующим сообщением.\n\n"
            "Как получить токен: @BotFather -> /newbot",
            make_token_help_keyboard(),
        )

    if callback_data.startswith("create_manager_bot:"):
        project_id = callback_data.split(":", 1)[1]
        await _set_data(chat_id, {"project_id": project_id})
        await _set_state(chat_id, STATE_AWAIT_MANAGER_TOKEN)
        return (
            "Отправьте токен менеджерского бота следующим сообщением.\n\n"
            "Как получить токен: @BotFather -> /newbot",
            make_token_help_keyboard(),
        )

    if callback_data.startswith("knowledge:"):
        project_id = callback_data.split(":", 1)[1]
        await _set_data(chat_id, {"project_id": project_id})
        await _set_state(chat_id, STATE_AWAIT_KNOWLEDGE_FILE)
        return (
            "Отправьте файл с документами (PDF, DOCX, TXT).\n"
            "Я обработаю его и добавлю в базу знаний проекта.",
            make_back_keyboard(f"project:{project_id}"),
        )

    if callback_data.startswith("managers:"):
        project_id = callback_data.split(":", 1)[1]
        team = await PlatformBotService(pool).get_project_team(project_id)
        manager_members = team.members
        legacy_targets = team.legacy_targets
        if manager_members or legacy_targets:
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

            text = "\n".join(lines) + "\n\nВведите ChatID нового менеджера:"
        else:
            text = "В проекте пока нет менеджеров.\n\nВведите ChatID первого менеджера:"

        await _set_data(chat_id, {"project_id": project_id})
        await _set_state(chat_id, STATE_AWAIT_ADD_MANAGER)
        return text, make_back_keyboard(f"project:{project_id}")

    if callback_data.startswith("detach_bot:"):
        project_id = callback_data.split(":", 1)[1]
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("Клиентского", callback_data=f"detach_client:{project_id}")],
            [InlineKeyboardButton("Менеджерского", callback_data=f"detach_manager:{project_id}")],
            [InlineKeyboardButton("Назад", callback_data=f"project:{project_id}")],
        ])
        return "Какого бота открепить?", keyboard

    if callback_data.startswith("detach_client:"):
        project_id = callback_data.split(":", 1)[1]
        project_repo = ProjectRepository(pool)
        await project_repo.set_bot_token(project_id, None)
        await project_repo.upsert_project_channel(project_id, kind="client", provider="telegram", status="disabled", config_json={"token_configured": False})
        return "Клиентский бот откреплен.", await _get_project_menu_keyboard(project_id, pool)

    if callback_data.startswith("detach_manager:"):
        project_id = callback_data.split(":", 1)[1]
        project_repo = ProjectRepository(pool)
        await project_repo.set_manager_bot_token(project_id, None)
        await project_repo.upsert_project_channel(project_id, kind="manager", provider="telegram", status="disabled", config_json={"token_configured": False})
        return "Менеджерский бот откреплен.", await _get_project_menu_keyboard(project_id, pool)

    if callback_data.startswith("delete:"):
        project_id = callback_data.split(":", 1)[1]
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT name FROM projects WHERE id = $1", ensure_uuid(project_id))
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

    if callback_data == "back_to_main":
        await _clear_state(chat_id)
        return await _cmd_start()

    if callback_data.startswith("back_to_project:"):
        project_id = callback_data.split(":", 1)[1]
        await _clear_state(chat_id)
        return await _show_project_menu(chat_id, project_id, pool)

    return "Неизвестная кнопка.", None


async def _verify_token(token: str) -> Optional[str]:
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
            if resp.status_code == 200 and resp.json().get("ok"):
                return resp.json()["result"]["username"]
        except Exception:
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


async def _set_manager_token(project_id: str, token: str, admin_chat_id: str, pool) -> None:
    project_repo = ProjectRepository(pool)
    await project_repo.set_manager_bot_token(project_id, token)
    user_repo = UserRepository(pool)
    admin_user_id, _ = await user_repo.get_or_create_by_telegram(int(admin_chat_id), first_name="", username=None)
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


async def _get_bot_username(token: str) -> Optional[str]:
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
            if resp.status_code == 200 and resp.json().get("ok"):
                return resp.json()["result"]["username"]
        except Exception:
            return None
    return None


async def _show_projects_list(chat_id: str, pool) -> AdminResponse:
    rows = [
        {"id": project.id, "name": project.name}
        for project in (await PlatformBotService(pool).list_projects_for_telegram_user(int(chat_id))).projects
        if str(project.id) != str(settings.ADMIN_PROJECT_ID)
    ]

    if not rows:
        text = "У вас пока нет проектов. Создайте первый."
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Новый проект", callback_data="newproject")]])
        return text, keyboard

    projects = [(str(row["id"]), row["name"]) for row in rows]
    return "Ваши проекты:", make_projects_list_keyboard(projects)


async def _show_project_menu(chat_id: str, project_id: str, pool) -> AdminResponse:
    project_repo = ProjectRepository(pool)

    async with pool.acquire() as conn:
        name_row = await conn.fetchrow("SELECT name FROM projects WHERE id = $1", ensure_uuid(project_id))
        if not name_row:
            return "Проект не найден.", None
        project_name = name_row["name"]

    settings_dict = await project_repo.get_project_settings(project_id)
    if not settings_dict:
        return "Не удалось получить настройки проекта.", None

    has_client = bool(settings_dict.get("bot_token"))
    has_manager = bool(settings_dict.get("manager_bot_token"))

    lines = [f"Проект: {project_name}"]
    if has_client and has_manager:
        lines.append("Проект настроен полностью.")
        client_username = await _get_bot_username(settings_dict["bot_token"])
        manager_username = await _get_bot_username(settings_dict["manager_bot_token"])
        if client_username:
            lines.append(f"Клиентский бот: @{client_username}")
        if manager_username:
            lines.append(f"Менеджерский бот: @{manager_username}")
    else:
        lines.append("Проект настроен не полностью.")
        if has_client:
            client_username = await _get_bot_username(settings_dict["bot_token"])
            lines.append(f"Клиентский бот: @{client_username}" if client_username else "Клиентский бот: токен установлен")
        if has_manager:
            manager_username = await _get_bot_username(settings_dict["manager_bot_token"])
            lines.append(f"Менеджерский бот: @{manager_username}" if manager_username else "Менеджерский бот: токен установлен")

    return "\n".join(lines), make_project_dynamic_keyboard(project_id, has_client, has_manager)


async def _get_project_menu_keyboard(project_id: str, pool) -> InlineKeyboardMarkup:
    project_repo = ProjectRepository(pool)
    settings_dict = await project_repo.get_project_settings(project_id)
    has_client = bool(settings_dict.get("bot_token")) if settings_dict else False
    has_manager = bool(settings_dict.get("manager_bot_token")) if settings_dict else False
    return make_project_dynamic_keyboard(project_id, has_client, has_manager)
