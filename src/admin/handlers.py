"""
Admin command handlers for managing projects via Telegram.
Implements the new UI flow with main menu, project listing, and dynamic menus.
"""

import uuid
import httpx
import asyncpg
import json
import re
from typing import Optional, Dict, Any, Tuple, List

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.database.repositories.project_repository import ProjectRepository
from src.database.repositories.template_repository import TemplateRepository
from src.database.repositories.knowledge_repository import KnowledgeRepository
from src.core.logging import get_logger
from src.core.config import settings
from src.services.redis_client import get_redis_client
from src.admin.keyboards import (
    make_main_menu_keyboard,
    make_projects_list_keyboard,
    make_project_dynamic_keyboard,
    make_template_keyboard,
    make_back_keyboard,
    make_token_help_keyboard,
)

logger = get_logger(__name__)

# =============================================================================
# TYPE DEFINITIONS
# =============================================================================
AdminResponse = Tuple[str, Optional[InlineKeyboardMarkup]]

# =============================================================================
# REDIS KEY PREFIXES & STATE CONSTANTS
# =============================================================================
STATE_PREFIX = "admin_state:"
DATA_PREFIX = "admin_data:"

STATE_IDLE = "idle"
STATE_AWAIT_PROJECT_NAME = "await_project_name"
STATE_AWAIT_CLIENT_TOKEN = "await_client_token"
STATE_AWAIT_CLIENT_TEMPLATE = "await_client_template"
STATE_AWAIT_MANAGER_TOKEN = "await_manager_token"
STATE_AWAIT_ADD_MANAGER = "await_add_manager"
STATE_DELETE_AWAIT_CONFIRM = "delete:await_confirm"
STATE_AWAIT_DETACH_CHOICE = "await_detach_choice"
STATE_AWAIT_KNOWLEDGE_FILE = "await_knowledge_file"

# =============================================================================
# REDIS HELPERS
# =============================================================================
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

# =============================================================================
# COMMAND HANDLERS
# =============================================================================
async def handle_admin_command(text: str, pool) -> AdminResponse:
    parts = text.strip().split()
    if not parts:
        return "Пустая команда.", None

    cmd = parts[0].lower()
    logger.info("Admin command received", extra={"cmd": cmd, "args": parts[1:]})

    if cmd == "/start":
        return await _cmd_start()
    elif cmd == "/help":
        return _cmd_help(), None
    # All other commands are handled as steps if in a state
    return await _process_admin_step(text, None, pool, None, None)

async def _cmd_start() -> AdminResponse:
    """Return main menu with two buttons."""
    text = "👋 Добро пожаловать в админ-панель фабрики ботов!"
    return text, make_main_menu_keyboard()

def _cmd_help() -> str:
    return (
        "📚 **Справка**\n"
        "/start — Главное меню\n"
        "Используйте кнопки для управления."
    )

# =============================================================================
# INTERACTIVE STEP HANDLING
# =============================================================================
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
    state: Optional[str] = None
) -> AdminResponse:
    if chat_id is None or state is None:
        return "❌ Ошибка состояния. Напишите /start.", None

    logger.debug("Processing step", extra={"chat_id": chat_id, "state": state, "text": text[:30]})

    if text.strip() == "/start":
        await _clear_state(chat_id)
        return await _cmd_start()

    if state == STATE_AWAIT_PROJECT_NAME:
        return await _step_await_project_name(chat_id, text, pool)
    elif state == STATE_AWAIT_CLIENT_TOKEN:
        return await _step_await_client_token(chat_id, text, pool)
    elif state == STATE_AWAIT_CLIENT_TEMPLATE:
        return await _step_await_client_template(chat_id, text, pool)
    elif state == STATE_AWAIT_MANAGER_TOKEN:
        return await _step_await_manager_token(chat_id, text, pool)
    elif state == STATE_AWAIT_ADD_MANAGER:
        return await _step_await_add_manager(chat_id, text, pool)
    elif state == STATE_DELETE_AWAIT_CONFIRM:
        return await _step_delete_confirm(chat_id, text, pool)
    elif state == STATE_AWAIT_DETACH_CHOICE:
        return await _step_detach_choice(chat_id, text, pool)
    elif state == STATE_AWAIT_KNOWLEDGE_FILE:
        return await _step_await_knowledge_file(chat_id, text, pool)

    await _clear_state(chat_id)
    return "❌ Диалог сброшен. Напишите /start.", None

# =============================================================================
# STEP IMPLEMENTATIONS
# =============================================================================
async def _step_await_project_name(chat_id: str, name: str, pool) -> AdminResponse:
    """Create a new project with unique name for this owner."""
    owner_id = chat_id
    async with pool.acquire() as conn:
        # Check uniqueness for this owner with explicit type cast
        existing = await conn.fetchval(
            "SELECT 1 FROM projects WHERE name = $1 AND owner_id = $2::text AND id != $3",
            name, owner_id, settings.ADMIN_PROJECT_ID
        )
        if existing:
            return "❌ У вас уже есть проект с таким именем. Придумайте другое.", None

    # Create project with owner_id = chat_id
    project_id = await _create_project_raw(name, owner_id, pool)
    await _clear_state(chat_id)
    # Show project menu
    return await _show_project_menu(chat_id, project_id, pool)

async def _step_await_client_token(chat_id: str, token: str, pool) -> AdminResponse:
    """Handle token input for client bot."""
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    if not project_id:
        await _clear_state(chat_id)
        return "❌ Ошибка: проект не указан.", None

    username = await _verify_token(token)
    if not username:
        return "❌ Неверный токен. Попробуйте еще раз.", make_token_help_keyboard()

    data["client_token"] = token
    data["client_username"] = username
    await _set_data(chat_id, data)
    await _set_state(chat_id, STATE_AWAIT_CLIENT_TEMPLATE)
    return "🎯 Выберите шаблон:", make_template_keyboard()

async def _step_await_client_template(chat_id: str, choice: str, pool) -> AdminResponse:
    """Handle template selection for client bot."""
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    client_token = data.get("client_token")
    if not project_id or not client_token:
        await _clear_state(chat_id)
        return "❌ Данные утеряны. Начните заново.", None

    # Extract slug if it's a callback
    if choice.startswith("tpl:"):
        template_slug = choice.replace("tpl:", "")
    else:
        template_slug = choice

    # Handle custom/skip
    if template_slug.lower() in ("custom", "skip"):
        await _set_project_token(project_id, client_token, pool)
        await _clear_state(chat_id)
        return await _show_project_menu(chat_id, project_id, pool)

    # Apply template
    template_repo = TemplateRepository(pool)
    template = await template_repo.get_by_slug(template_slug)
    if not template:
        return "❌ Шаблон не найден. Выберите кнопку.", make_template_keyboard()

    await _set_project_token(project_id, client_token, pool)
    await ProjectRepository(pool).apply_template(project_id, template_slug)
    await _clear_state(chat_id)
    return await _show_project_menu(chat_id, project_id, pool)

async def _step_await_manager_token(chat_id: str, token: str, pool) -> AdminResponse:
    """Handle token input for manager bot."""
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    if not project_id:
        await _clear_state(chat_id)
        return "❌ Ошибка: проект не указан.", None

    username = await _verify_token(token)
    if not username:
        return "❌ Неверный токен. Попробуйте еще раз.", make_token_help_keyboard()

    # Set manager token and add current user as first manager
    await _set_manager_token(project_id, token, chat_id, pool)
    await _clear_state(chat_id)

    text = f"✅ Менеджерский бот создан! Ссылка: @{username}\n\nЧтобы добавить других менеджеров, нажмите кнопку 'Менеджеры'."
    keyboard = await _get_project_menu_keyboard(project_id, pool)
    return text, keyboard

async def _step_await_add_manager(chat_id: str, manager_id: str, pool) -> AdminResponse:
    """Add a new manager to the project."""
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    if not project_id:
        await _clear_state(chat_id)
        return "❌ Ошибка: проект не указан.", None

    # Validate numeric (Telegram chat IDs can be negative for groups, but we accept any integer)
    if not manager_id.strip().lstrip('-').isdigit():
        return "❌ ChatID должен быть числом. Попробуйте еще раз.", None

    try:
        await ProjectRepository(pool).add_manager(project_id, manager_id.strip())
    except Exception as e:
        logger.exception("Failed to add manager", extra={"error": str(e)})
        return f"❌ Ошибка: {str(e)}", None

    await _clear_state(chat_id)
    return f"✅ Менеджер {manager_id} зарегистрирован!", await _get_project_menu_keyboard(project_id, pool)

async def _step_delete_confirm(chat_id: str, text: str, pool) -> AdminResponse:
    """Confirm project deletion."""
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    project_name = data.get("project_name")

    if not project_id:
        await _clear_state(chat_id)
        return "❌ Ошибка: проект не найден.", None

    if text.strip().lower() == "да":
        try:
            async with pool.acquire() as conn:
                await conn.execute("DELETE FROM projects WHERE id = $1", uuid.UUID(project_id))
            logger.info("Project deleted", extra={"project_id": project_id, "name": project_name})
            await _clear_state(chat_id)
            return f"✅ Проект **«{project_name}»** ({project_id}) успешно удален.", None
        except Exception as e:
            logger.error("Failed to delete project", extra={"error": str(e)})
            await _clear_state(chat_id)
            return f"❌ Ошибка при удалении: {str(e)}", None
    else:
        await _clear_state(chat_id)
        return "❌ Удаление отменено.", None

async def _step_detach_choice(chat_id: str, choice: str, pool) -> AdminResponse:
    """Handle detach bot choice."""
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    if not project_id:
        await _clear_state(chat_id)
        return "❌ Ошибка: проект не указан.", None

    if choice == "client":
        await ProjectRepository(pool).set_bot_token(project_id, None)
        await _clear_state(chat_id)
        return "✅ Клиентский бот откреплён.", await _get_project_menu_keyboard(project_id, pool)
    elif choice == "manager":
        await ProjectRepository(pool).set_manager_bot_token(project_id, None)
        await _clear_state(chat_id)
        return "✅ Менеджерский бот откреплён.", await _get_project_menu_keyboard(project_id, pool)
    else:
        await _clear_state(chat_id)
        return "❌ Отмена.", await _get_project_menu_keyboard(project_id, pool)

# =============================================================================
# CALLBACK HANDLER
# =============================================================================
async def handle_admin_callback(callback_data: str, chat_id: str, pool) -> AdminResponse:
    logger.info("Callback", extra={"data": callback_data, "chat_id": chat_id})

    if callback_data == "newproject":
        await _set_state(chat_id, STATE_AWAIT_PROJECT_NAME)
        return "✍️ **Введите название нового проекта** (например: Идея на миллион):", make_back_keyboard()

    elif callback_data == "listprojects":
        return await _show_projects_list(chat_id, pool)

    elif callback_data.startswith("project:"):
        project_id = callback_data.split(":", 1)[1]
        return await _show_project_menu(chat_id, project_id, pool)

    elif callback_data.startswith("create_client_bot:"):
        project_id = callback_data.split(":", 1)[1]
        await _set_data(chat_id, {"project_id": project_id})
        await _set_state(chat_id, STATE_AWAIT_CLIENT_TOKEN)
        return (
            "🔑 **Отправьте токен клиентского бота** следующим сообщением.\n\n"
            "Как получить токен: @BotFather → /newbot",
            make_token_help_keyboard()
        )

    elif callback_data.startswith("create_manager_bot:"):
        project_id = callback_data.split(":", 1)[1]
        await _set_data(chat_id, {"project_id": project_id})
        await _set_state(chat_id, STATE_AWAIT_MANAGER_TOKEN)
        return (
            "🔑 **Отправьте токен менеджерского бота** следующим сообщением.\n\n"
            "Как получить токен: @BotFather → /newbot",
            make_token_help_keyboard()
        )

    elif callback_data.startswith("knowledge:"):
        project_id = callback_data.split(":", 1)[1]
        await _set_data(chat_id, {"project_id": project_id})
        await _set_state(chat_id, STATE_AWAIT_KNOWLEDGE_FILE)
        return (
            "📚 **Отправьте файл с документами** (PDF, DOCX, TXT).\n"
            "Я обработаю его и добавлю в базу знаний проекта.",
            make_back_keyboard(f"project:{project_id}")
        )

    elif callback_data.startswith("managers:"):
        project_id = callback_data.split(":", 1)[1]
        # List existing managers
        managers = await ProjectRepository(pool).get_managers(project_id)
        if managers:
            lines = ["👥 **Менеджеры проекта**:"] + [f"• `{m}`" for m in managers]
            text = "\n".join(lines) + "\n\n📝 Введите ChatID нового менеджера (число):"
        else:
            text = "📭 В проекте пока нет менеджеров.\n\n📝 Введите ChatID первого менеджера (число):"

        await _set_data(chat_id, {"project_id": project_id})
        await _set_state(chat_id, STATE_AWAIT_ADD_MANAGER)
        return text, make_back_keyboard(f"project:{project_id}")

    elif callback_data.startswith("detach_bot:"):
        project_id = callback_data.split(":", 1)[1]
        # Show options to detach client or manager
        text = "🔗 Какого бота открепить?"
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("🤖 Клиентского", callback_data=f"detach_client:{project_id}")],
            [InlineKeyboardButton("👥 Менеджерского", callback_data=f"detach_manager:{project_id}")],
            [InlineKeyboardButton("🔙 Назад", callback_data=f"project:{project_id}")],
        ])
        return text, keyboard

    elif callback_data.startswith("detach_client:"):
        project_id = callback_data.split(":", 1)[1]
        await ProjectRepository(pool).set_bot_token(project_id, None)
        return "✅ Клиентский бот откреплён.", await _get_project_menu_keyboard(project_id, pool)

    elif callback_data.startswith("detach_manager:"):
        project_id = callback_data.split(":", 1)[1]
        await ProjectRepository(pool).set_manager_bot_token(project_id, None)
        return "✅ Менеджерский бот откреплён.", await _get_project_menu_keyboard(project_id, pool)

    elif callback_data.startswith("delete:"):
        project_id = callback_data.split(":", 1)[1]
        # Fetch project name
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT name FROM projects WHERE id = $1", uuid.UUID(project_id))
            if not row:
                return "❌ Проект не найден.", None
            pname = row["name"]

        await _set_data(chat_id, {"project_id": project_id, "project_name": pname})
        await _set_state(chat_id, STATE_DELETE_AWAIT_CONFIRM)
        text = (
            f"🗑️ **Вы уверены, что хотите удалить проект?**\n\n"
            f"Название: **{pname}**\n"
            f"ID: `{project_id}`\n\n"
            f"⚠️ Это действие НЕОБРАТИМО! Все данные будут удалены.\n\n"
            f"Для подтверждения введите слово **да** (без кавычек)."
        )
        return text, make_back_keyboard(f"project:{project_id}")

    elif callback_data.startswith("tpl:"):
        # If we are in template selection state, handle via step
        state = await _get_state(chat_id)
        if state == STATE_AWAIT_CLIENT_TEMPLATE:
            return await _process_admin_step(callback_data, await _get_data(chat_id), pool, chat_id, state)
        else:
            return "❌ Неверный контекст.", None

    elif callback_data == "back_to_main":
        await _clear_state(chat_id)
        return await _cmd_start()

    elif callback_data.startswith("back_to_project:"):
        project_id = callback_data.split(":", 1)[1]
        await _clear_state(chat_id)
        return await _show_project_menu(chat_id, project_id, pool)

    return "❌ Неизвестная кнопка.", None

# =============================================================================
# HELPERS
# =============================================================================
async def _verify_token(token: str) -> Optional[str]:
    """Verify token with Telegram and return bot username if valid."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"https://api.telegram.org/bot{token}/getMe", timeout=10)
            if resp.status_code == 200 and resp.json().get("ok"):
                return resp.json()["result"]["username"]
        except Exception:
            pass
    return None

async def _create_project_raw(name: str, owner_id: str, pool) -> str:
    """
    Insert a new project with given owner_id (Telegram chat_id).
    Returns the new project's UUID as string.
    Uses explicit type cast to text for owner_id.
    """
    logger.info("Creating project", extra={"name": name, "owner_id": owner_id})
    async with pool.acquire() as conn:
        project_id = await conn.fetchval("""
            INSERT INTO projects (id, name, owner_id, bot_token, system_prompt)
            VALUES (gen_random_uuid(), $1, $2::text, '', 'Ты — полезный AI-ассистент.')
            RETURNING id
        """, name, owner_id)
    logger.info("Project created", extra={"project_id": project_id})
    return str(project_id)

async def _set_project_token(project_id: str, token: str, pool) -> None:
    """Set bot token and configure webhook."""
    secret_token = uuid.uuid4().hex
    project_repo = ProjectRepository(pool)
    await project_repo.set_bot_token(project_id, token)
    await project_repo.set_webhook_secret(project_id, secret_token)

    base_url = settings.RENDER_EXTERNAL_URL or settings.PUBLIC_URL
    if not base_url:
        raise ValueError("PUBLIC_URL not set")

    webhook_url = f"{base_url.rstrip('/')}/webhook/{project_id}"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": webhook_url, "secret_token": secret_token}
        )
        if resp.status_code != 200 or not resp.json().get("ok"):
            raise Exception(f"Webhook setup failed: {resp.text}")

async def _set_manager_token(project_id: str, token: str, admin_chat_id: str, pool) -> None:
    """Set manager bot token, add admin as manager, and set webhook."""
    project_repo = ProjectRepository(pool)
    await project_repo.set_manager_bot_token(project_id, token)
    await project_repo.add_manager(project_id, admin_chat_id)

    # Generate and set manager webhook secret
    manager_secret = uuid.uuid4().hex
    await project_repo.set_manager_webhook_secret(project_id, manager_secret)

    base_url = settings.RENDER_EXTERNAL_URL or settings.PUBLIC_URL
    webhook_url = f"{base_url.rstrip('/')}/manager/webhook"
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"https://api.telegram.org/bot{token}/setWebhook",
            json={"url": webhook_url, "secret_token": manager_secret}
        )
        if resp.status_code != 200 or not resp.json().get("ok"):
            raise Exception(f"Manager webhook setup failed: {resp.text}")

async def _get_bot_username(token: str) -> Optional[str]:
    """Fetch bot username using getMe."""
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"https://api.telegram.org/bot{token}/getMe", timeout=5)
            if resp.status_code == 200 and resp.json().get("ok"):
                return resp.json()["result"]["username"]
        except:
            pass
    return None

async def _show_projects_list(chat_id: str, pool) -> AdminResponse:
    """Show list of projects belonging to this owner (excluding admin project) as buttons."""
    owner_id = chat_id
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, name FROM projects
            WHERE owner_id = $1::text AND id != $2
            ORDER BY created_at DESC
        """, owner_id, settings.ADMIN_PROJECT_ID)

    if not rows:
        text = "📭 У вас пока нет проектов. Создайте первый!"
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("➕ Новый проект", callback_data="newproject")
        ]])
        return text, keyboard

    projects = [(str(r["id"]), r["name"]) for r in rows]
    return "📦 **Ваши проекты**:", make_projects_list_keyboard(projects)

async def _show_project_menu(chat_id: str, project_id: str, pool) -> AdminResponse:
    """Display project context menu with dynamic buttons."""
    project_repo = ProjectRepository(pool)

    # Get project name
    async with pool.acquire() as conn:
        name_row = await conn.fetchrow("SELECT name FROM projects WHERE id = $1", uuid.UUID(project_id))
        if not name_row:
            return "❌ Проект не найден.", None
        project_name = name_row["name"]

    # Get project settings (contains tokens, etc.)
    settings_dict = await project_repo.get_project_settings(project_id)
    if not settings_dict:
        return "❌ Не удалось получить настройки проекта.", None

    has_client = bool(settings_dict.get("bot_token"))
    has_manager = bool(settings_dict.get("manager_bot_token"))

    # Build message
    lines = [f"📁 **Проект: {project_name}**"]
    if has_client and has_manager:
        lines.append("✅ Проект настроен полностью.")
        client_username = await _get_bot_username(settings_dict["bot_token"])
        manager_username = await _get_bot_username(settings_dict["manager_bot_token"])
        if client_username:
            lines.append(f"🤖 Клиентский бот: @{client_username}")
        if manager_username:
            lines.append(f"👥 Менеджерский бот: @{manager_username}")
    else:
        lines.append("⚠️ Проект не настроен полностью.")
        if has_client:
            client_username = await _get_bot_username(settings_dict["bot_token"])
            lines.append(f"🤖 Клиентский бот: @{client_username}" if client_username else "🤖 Клиентский бот: токен установлен")
        if has_manager:
            manager_username = await _get_bot_username(settings_dict["manager_bot_token"])
            lines.append(f"👥 Менеджерский бот: @{manager_username}" if manager_username else "👥 Менеджерский бот: токен установлен")

    text = "\n".join(lines)
    keyboard = make_project_dynamic_keyboard(project_id, has_client, has_manager)
    return text, keyboard

async def _get_project_menu_keyboard(project_id: str, pool) -> InlineKeyboardMarkup:
    """Helper to get project keyboard without message."""
    project_repo = ProjectRepository(pool)
    settings_dict = await project_repo.get_project_settings(project_id)
    has_client = bool(settings_dict.get("bot_token")) if settings_dict else False
    has_manager = bool(settings_dict.get("manager_bot_token")) if settings_dict else False
    return make_project_dynamic_keyboard(project_id, has_client, has_manager)

# =============================================================================
# LEGACY COMMANDS (kept for compatibility, but not used in new UI)
# =============================================================================
async def cmd_listprojects(pool) -> str:
    """Legacy command - not used in new flow."""
    return "Используйте кнопку 'Мои проекты' в меню."

async def cmd_settoken(project_id: str, token: str, pool) -> str:
    """Legacy command - not used in new flow."""
    return "Используйте создание клиентского бота через меню проекта."

async def cmd_setmanager(project_id: str, manager_token: str, manager_chat_id: Optional[str], pool) -> str:
    """Legacy command - not used in new flow."""
    return "Используйте создание менеджерского бота через меню проекта."

async def cmd_listmanagers(project_id: str, pool) -> str:
    """Legacy command - not used in new flow."""
    return "Используйте кнопку 'Менеджеры' в меню проекта."

async def cmd_set_pro_mode(project_id: str, enabled: bool, pool) -> str:
    """Legacy command - not used in new flow."""
    return "Pro-режим настраивается в конструкторе."
