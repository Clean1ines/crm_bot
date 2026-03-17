"""
Admin command handlers for managing projects via Telegram.

Supports both command-based and interactive step-by-step flows using Redis for state.
Provides wizard-style onboarding for project creation, token setup, and manager configuration.
"""

import uuid
import httpx
import asyncpg
import json
from typing import Optional, Dict, Any, List, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.database.repositories.project_repository import ProjectRepository
from src.database.repositories.template_repository import TemplateRepository
from src.core.logging import get_logger
from src.core.config import settings
from src.services.redis_client import get_redis_client

logger = get_logger(__name__)

# =============================================================================
# TYPE DEFINITIONS
# =============================================================================
AdminResponse = Tuple[str, Optional[InlineKeyboardMarkup]]
"""Return type for all admin handlers: (response_text, optional_inline_keyboard)."""

# =============================================================================
# REDIS KEY PREFIXES & STATE CONSTANTS
# =============================================================================
STATE_PREFIX = "admin_state:"
DATA_PREFIX = "admin_data:"

STATE_IDLE = "idle"
STATE_NEWPROJECT_AWAIT_NAME = "newproject:await_name"
STATE_NEWPROJECT_AWAIT_TEMPLATE = "newproject:await_template"
STATE_SETTOKEN_AWAIT_PROJECT = "settoken:await_project"
STATE_SETTOKEN_AWAIT_TOKEN = "settoken:await_token"
STATE_SETMANAGER_AWAIT_PROJECT = "setmanager:await_project"
STATE_SETMANAGER_AWAIT_TOKEN = "setmanager:await_token"
STATE_SETMANAGER_AWAIT_CHAT_ID = "setmanager:await_chat_id"
STATE_LISTMANAGERS_AWAIT_PROJECT = "listmanagers:await_project"
STATE_PROMODE_AWAIT_PROJECT = "promode:await_project"
STATE_PROMODE_AWAIT_ENABLED = "promode:await_enabled"

# =============================================================================
# KEYBOARD FACTORIES (NEW — reusable inline keyboards)
# =============================================================================
def _make_main_menu_keyboard() -> InlineKeyboardMarkup:
    """
    Create the main menu inline keyboard for /start command.
    
    Returns:
        InlineKeyboardMarkup with buttons: Create Bot, My Projects, Settings, Help.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🚀 Создать бота", callback_data="newproject")],
        [InlineKeyboardButton("📦 Мои проекты", callback_data="listprojects")],
        [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
        [InlineKeyboardButton("❓ Помощь", callback_data="help")],
    ])


def _make_project_keyboard(project_id: str) -> InlineKeyboardMarkup:
    """
    Create project management keyboard for a specific project.
    
    Args:
        project_id: UUID of the project.
    
    Returns:
        InlineKeyboardMarkup with project-specific actions.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🔑 Установить токен", callback_data=f"settoken:{project_id}")],
        [InlineKeyboardButton("👥 Менеджеры", callback_data=f"managers:{project_id}")],
        [InlineKeyboardButton("📚 Загрузить знания", callback_data=f"knowledge:{project_id}")],
        [InlineKeyboardButton("🎨 Конструктор (Pro)", callback_data=f"promode:{project_id}")],
        [InlineKeyboardButton("🗑️ Удалить проект", callback_data=f"delete:{project_id}")],
    ])


def _make_template_keyboard() -> InlineKeyboardMarkup:
    """
    Create template selection keyboard for new project flow.
    
    Returns:
        InlineKeyboardMarkup with template options + skip button.
    """
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💬 Поддержка", callback_data="tpl:support")],
        [InlineKeyboardButton("🎯 Лиды", callback_data="tpl:leads")],
        [InlineKeyboardButton("🛒 Заказы", callback_data="tpl:orders")],
        [InlineKeyboardButton("⚙️ Свой (Pro)", callback_data="tpl:custom")],
        [InlineKeyboardButton("⏭️ Пропустить", callback_data="tpl:skip")],
    ])


def _make_token_help_keyboard() -> InlineKeyboardMarkup:
    """
    Create helper keyboard with token instructions link.
    
    Returns:
        InlineKeyboardMarkup with single help button.
    """
    return InlineKeyboardMarkup([[
        InlineKeyboardButton("📋 Как получить токен?", callback_data="help_token")
    ]])


def _make_token_input_hint() -> str:
    """
    Return formatted hint text for token input step.
    
    Returns:
        Markdown-formatted instruction text.
    """
    return (
        "📌 **Как получить токен бота?**\n"
        "1. Напишите @BotFather → /newbot\n"
        "2. Скопируйте токен (вида `123456:ABCdef...`)\n"
        "3. Отправьте его мне следующим сообщением"
    )

# =============================================================================
# REDIS HELPERS (unchanged logic, improved docstrings)
# =============================================================================
async def _get_state(chat_id: str) -> str:
    """
    Retrieve current state for a given chat_id from Redis.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
    
    Returns:
        Current state string or STATE_IDLE if none set.
    """
    redis = await get_redis_client()
    state = await redis.get(f"{STATE_PREFIX}{chat_id}")
    return state.decode() if state and isinstance(state, bytes) else (state or STATE_IDLE)


async def _set_state(chat_id: str, state: str):
    """
    Set current state for a chat_id with 10-minute TTL.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
        state: New state string to set.
    """
    redis = await get_redis_client()
    await redis.setex(f"{STATE_PREFIX}{chat_id}", 600, state)
    logger.debug("State set", extra={"chat_id": chat_id, "state": state})


async def _clear_state(chat_id: str):
    """
    Clear both state and data for a chat_id from Redis.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
    """
    redis = await get_redis_client()
    await redis.delete(f"{STATE_PREFIX}{chat_id}")
    await redis.delete(f"{DATA_PREFIX}{chat_id}")
    logger.debug("State cleared", extra={"chat_id": chat_id})


async def _get_data(chat_id: str) -> Dict[str, Any]:
    """
    Retrieve JSON data associated with current state from Redis.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
    
    Returns:
        Stored data dict or empty dict if none.
    """
    redis = await get_redis_client()
    data = await redis.get(f"{DATA_PREFIX}{chat_id}")
    if data:
        if isinstance(data, bytes):
            data = data.decode()
        return json.loads(data)
    return {}


async def _set_data(chat_id: str, data: Dict[str, Any]):
    """
    Store JSON data associated with current state in Redis (10-min TTL).
    
    Args:
        chat_id: Telegram chat ID of the admin user.
        data: Dict to store as JSON.
    """
    redis = await get_redis_client()
    await redis.setex(f"{DATA_PREFIX}{chat_id}", 600, json.dumps(data))
    logger.debug("Data stored", extra={"chat_id": chat_id, "data_keys": list(data.keys())})

# =============================================================================
# COMMAND HANDLERS — now return AdminResponse (text, keyboard)
# =============================================================================
async def handle_admin_command(text: str, pool) -> AdminResponse:
    """
    Parse admin command and return (response_text, optional_keyboard).
    
    Args:
        text: Full message text from admin.
        pool: Asyncpg connection pool.
    
    Returns:
        Tuple of response text and optional InlineKeyboardMarkup.
    """
    parts = text.strip().split()
    if not parts:
        return "Пустая команда.", None

    cmd = parts[0].lower()
    logger.info("Admin command received", extra={"cmd": cmd, "args": parts[1:]})

    if cmd == "/start":
        return await _cmd_start()
    elif cmd == "/help":
        return _cmd_help(), None
    elif cmd == "/newproject":
        if len(parts) < 2:
            return "Использование: /newproject <название>", None
        name = " ".join(parts[1:])
        return await cmd_newproject(name, pool), None
    elif cmd == "/settoken":
        if len(parts) != 3:
            return "Использование: /settoken <project_id> <bot_token>", None
        project_id, token = parts[1], parts[2]
        return await cmd_settoken(project_id, token, pool), None
    elif cmd == "/setmanager":
        if len(parts) < 3:
            return "Использование: /setmanager <project_id> <manager_token> [chat_id]", None
        project_id, manager_token = parts[1], parts[2]
        manager_chat_id = parts[3] if len(parts) > 3 else None
        return await cmd_setmanager(project_id, manager_token, manager_chat_id, pool), None
    elif cmd == "/listmanagers":
        if len(parts) != 2:
            return "Использование: /listmanagers <project_id>", None
        return await cmd_listmanagers(parts[1], pool), None
    elif cmd == "/removemanager":
        if len(parts) != 3:
            return "Использование: /removemanager <project_id> <chat_id>", None
        return await cmd_removemanager(parts[1], parts[2], pool), None
    elif cmd == "/listprojects":
        return await cmd_listprojects(pool), None
    elif cmd == "/promode":
        if len(parts) != 3:
            return "Использование: /promode <project_id> <on|off>", None
        project_id, enabled_str = parts[1], parts[2]
        enabled = enabled_str.lower() in ("on", "true", "1", "yes")
        return await cmd_set_pro_mode(project_id, enabled, pool), None
    else:
        # Не команда — возможно, шаг в диалоге
        return await _process_admin_step(text, None, pool, None, None)


async def _cmd_start() -> AdminResponse:
    """
    Return welcome message WITH inline keyboard markup.
    
    Returns:
        Tuple of welcome text and main menu keyboard.
    """
    text = (
        "👋 **Админ-панель фабрики ботов**\n\n"
        "Я помогу создать и настроить вашего AI-ассистента.\n\n"
        "🔹 **Быстрый старт**:\n"
        "1. Нажмите «🚀 Создать бота»\n"
        "2. Введите название проекта\n"
        "3. Выберите шаблон (или пропустите)\n"
        "4. Вставьте токен из @BotFather\n"
        "5. Готово! 🎉\n\n"
        "📌 Токен и настройки шифруются. Ваши данные в безопасности."
    )
    return text, _make_main_menu_keyboard()


def _cmd_help() -> str:
    """
    Return help message with available commands (text only).
    
    Returns:
        Formatted help text.
    """
    return (
        "📚 **Справка по командам**\n\n"
        "/start — главное меню с кнопками\n"
        "/newproject <название> — создать проект (текстовый режим)\n"
        "/settoken <id> <токен> — привязать токен бота\n"
        "/setmanager <id> <токен> [chat_id] — настроить менеджера\n"
        "/listmanagers <id> — показать менеджеров проекта\n"
        "/removemanager <id> <chat_id> — удалить менеджера\n"
        "/listprojects — список всех проектов\n"
        "/promode <id> <on|off> — включить Pro-режим (канвас)\n\n"
        "💡 **Совет**: используйте кнопки в /start — это быстрее!"
    )

# =============================================================================
# INTERACTIVE STEP HANDLING
# =============================================================================
async def handle_admin_step(chat_id: str, text: str, pool) -> Optional[AdminResponse]:
    """
    Process non-command message as part of interactive flow.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
        text: Message text from admin.
        pool: Asyncpg connection pool.
    
    Returns:
        Optional tuple of (response_text, keyboard) if flow is active.
    """
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
    """
    Process one step of interactive flow. Returns (text, keyboard).
    
    Args:
        text: User input text.
        data: Stored step data dict.
        pool: Asyncpg connection pool.
        chat_id: Telegram chat ID (optional for logging).
        state: Current state string (optional for logging).
    
    Returns:
        Tuple of response text and optional keyboard.
    """
    if chat_id is None or state is None:
        return "❌ Ошибка состояния. Начните с /start.", None

    logger.debug("Processing admin step", extra={"chat_id": chat_id, "state": state})

    if state == STATE_NEWPROJECT_AWAIT_NAME:
        return await _step_newproject_name(chat_id, text, pool)
    elif state == STATE_NEWPROJECT_AWAIT_TEMPLATE:
        return await _handle_template_selection(chat_id, text, pool)
    elif state == STATE_SETTOKEN_AWAIT_PROJECT:
        return await _step_settoken_project(chat_id, text, pool)
    elif state == STATE_SETTOKEN_AWAIT_TOKEN:
        return await _step_settoken_token(chat_id, text, pool)
    elif state == STATE_SETMANAGER_AWAIT_PROJECT:
        return await _step_setmanager_project(chat_id, text, pool)
    elif state == STATE_SETMANAGER_AWAIT_TOKEN:
        return await _step_setmanager_token(chat_id, text, pool)
    elif state == STATE_SETMANAGER_AWAIT_CHAT_ID:
        return await _step_setmanager_chat_id(chat_id, text, pool)
    elif state == STATE_LISTMANAGERS_AWAIT_PROJECT:
        return await _step_listmanagers_project(chat_id, text, pool), None
    elif state == STATE_PROMODE_AWAIT_PROJECT:
        return await _step_promode_project(chat_id, text, pool)
    elif state == STATE_PROMODE_AWAIT_ENABLED:
        return await _step_promode_enabled(chat_id, text, pool), None
    else:
        await _clear_state(chat_id)
        return "❌ Неизвестное состояние. Диалог сброшен. Используйте /start.", None

# =============================================================================
# STEP IMPLEMENTATIONS — all return AdminResponse
# =============================================================================
async def _step_newproject_start(chat_id: str) -> AdminResponse:
    """Start new project flow: ask for project name."""
    await _set_state(chat_id, STATE_NEWPROJECT_AWAIT_NAME)
    return "✍️ **Введите название нового проекта**:\n\n(например: `Пиццерия Москва`, `Юридическая консультация`)", None


async def _step_newproject_name(chat_id: str, name: str, pool) -> AdminResponse:
    """Process project name, create project, then show template selection."""
    project_id = await _create_project_raw(name, pool)
    await _set_data(chat_id, {"project_id": project_id})
    await _set_state(chat_id, STATE_NEWPROJECT_AWAIT_TEMPLATE)
    
    text = (
        f"✅ Проект **«{name}»** создан!\n"
        f"🆔 ID: `{project_id}`\n\n"
        f"🎯 **Выберите шаблон** (или пропустите):\n"
        f"• 💬 `support` — поддержка клиентов (ответы + эскалация)\n"
        f"• 🎯 `leads` — сбор лидов (контакты + CRM)\n"
        f"• 🛒 `orders` — приём заказов (меню + оформление)\n"
        f"• ⚙️ `custom` — пустой шаблон для Pro-канваса"
    )
    return text, _make_template_keyboard()


async def _handle_template_selection(chat_id: str, template_slug: str, pool) -> AdminResponse:
    """Handle template selection after project creation."""
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    
    if not project_id:
        await _clear_state(chat_id)
        return "❌ Ошибка: данные проекта утеряны. Начните заново.", None
    
    if template_slug.lower() in ("skip", "custom", "none", ""):
        await _clear_state(chat_id)
        text = (
            f"✅ Проект создан без шаблона.\n\n"
            f"🔑 **Следующий шаг**: установите токен бота:\n"
            f"1. Скопируйте токен из @BotFather\n"
            f"2. Отправьте его мне следующим сообщением\n\n"
            f"💡 Pro-режим (канвас): `/promode {project_id} on`"
        )
        return text, _make_token_help_keyboard()
    
    template_repo = TemplateRepository(pool)
    template = await template_repo.get_by_slug(template_slug.replace("tpl:", ""))
    
    if not template:
        return "❌ Шаблон не найден. Выберите из кнопок или введите `skip`.", _make_template_keyboard()
    
    project_repo = ProjectRepository(pool)
    success = await project_repo.apply_template(project_id, template_slug.replace("tpl:", ""))
    
    if not success:
        await _clear_state(chat_id)
        return "❌ Не удалось применить шаблон. Попробуйте ещё раз.", None
    
    await _clear_state(chat_id)
    
    text = (
        f"✅ Шаблон **«{template['name']}»** применён!\n"
        f"📝 {template['description']}\n\n"
        f"🔑 **Теперь вставьте токен бота**:\n"
        f"1. @BotFather → /newbot → скопируйте токен\n"
        f"2. Отправьте токен мне следующим сообщением"
    )
    return text, _make_token_help_keyboard()


async def _step_settoken_start(chat_id: str) -> AdminResponse:
    """Start set token flow: ask for project ID."""
    await _set_state(chat_id, STATE_SETTOKEN_AWAIT_PROJECT)
    return "🆔 **Введите ID проекта**:\n\n(получите через /listprojects или из сообщения о создании)", None


async def _step_settoken_project(chat_id: str, project_id: str, pool) -> AdminResponse:
    """Validate project exists, store ID, then ask for token."""
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM projects WHERE id = $1", uuid.UUID(project_id))
        if not exists:
            return f"❌ Проект `{project_id}` не найден.", None
    
    await _set_data(chat_id, {"project_id": project_id})
    await _set_state(chat_id, STATE_SETTOKEN_AWAIT_TOKEN)
    return _make_token_input_hint(), None


async def _step_settoken_token(chat_id: str, token: str, pool) -> AdminResponse:
    """Set token for project, then show project menu."""
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    
    if not project_id:
        await _clear_state(chat_id)
        return "❌ Ошибка: проект не указан.", None
    
    result = await cmd_settoken(project_id, token, pool)
    await _clear_state(chat_id)
    
    # После успешной установки токена — показываем меню проекта
    keyboard = _make_project_keyboard(project_id)
    return result, keyboard


async def _step_setmanager_start(chat_id: str) -> AdminResponse:
    """Start set manager flow: ask for project ID."""
    await _set_state(chat_id, STATE_SETMANAGER_AWAIT_PROJECT)
    return "🆔 **Введите ID проекта**:", None


async def _step_setmanager_project(chat_id: str, project_id: str, pool) -> AdminResponse:
    """Validate project, store ID, then ask for manager bot token."""
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM projects WHERE id = $1", uuid.UUID(project_id))
        if not exists:
            return f"❌ Проект `{project_id}` не найден.", None
    await _set_data(chat_id, {"project_id": project_id})
    await _set_state(chat_id, STATE_SETMANAGER_AWAIT_TOKEN)
    return "🔑 **Введите токен менеджерского бота**:\n\n(создайте через @BotFather → /newbot)", None


async def _step_setmanager_token(chat_id: str, manager_token: str, pool) -> AdminResponse:
    """Store manager token, then ask for manager chat ID."""
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    if not project_id:
        await _clear_state(chat_id)
        return "❌ Ошибка: проект не указан.", None
    await _set_data(chat_id, {"project_id": project_id, "manager_token": manager_token})
    await _set_state(chat_id, STATE_SETMANAGER_AWAIT_CHAT_ID)
    return "👤 **Введите chat_id менеджера**:\n\n(получите через @echoManagersBot → /start)", None


async def _step_setmanager_chat_id(chat_id: str, manager_chat_id: str, pool) -> AdminResponse:
    """Set manager token and chat ID, then show project menu."""
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    manager_token = data.get("manager_token")
    if not project_id or not manager_token:
        await _clear_state(chat_id)
        return "❌ Ошибка: данные утеряны.", None
    result = await cmd_setmanager(project_id, manager_token, manager_chat_id, pool)
    await _clear_state(chat_id)
    return result, _make_project_keyboard(project_id)


async def _step_listmanagers_project(chat_id: str, project_id: str, pool) -> str:
    """Show managers for project (text only, no keyboard)."""
    result = await cmd_listmanagers(project_id, pool)
    await _clear_state(chat_id)
    return result


async def _step_promode_start(chat_id: str) -> AdminResponse:
    """Start Pro mode toggle flow: ask for project ID."""
    await _set_state(chat_id, STATE_PROMODE_AWAIT_PROJECT)
    return "🆔 **Введите ID проекта**:", None


async def _step_promode_project(chat_id: str, project_id: str, pool) -> AdminResponse:
    """Validate project, store ID, then ask for on/off."""
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM projects WHERE id = $1", uuid.UUID(project_id))
        if not exists:
            return f"❌ Проект `{project_id}` не найден.", None
    await _set_data(chat_id, {"project_id": project_id})
    await _set_state(chat_id, STATE_PROMODE_AWAIT_ENABLED)
    return "⚙️ **Введите `on` для включения Pro или `off` для отключения**:", None


async def _step_promode_enabled(chat_id: str, value: str, pool) -> AdminResponse:
    """Set Pro mode enabled/disabled, then show project menu."""
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    if not project_id:
        await _clear_state(chat_id)
        return "❌ Ошибка: проект не указан.", None
    enabled = value.lower() in ("on", "true", "1", "yes", "enable", "enabled")
    result = await cmd_set_pro_mode(project_id, enabled, pool)
    await _clear_state(chat_id)
    return result, _make_project_keyboard(project_id)

# =============================================================================
# CALLBACK HANDLER — returns AdminResponse
# =============================================================================
async def handle_admin_callback(callback_data: str, chat_id: str, pool) -> AdminResponse:
    """
    Handle inline button callbacks. Returns (text, keyboard).
    
    Args:
        callback_data: Callback data string from button press.
        chat_id: Telegram chat ID of the admin user.
        pool: Asyncpg connection pool.
    
    Returns:
        Tuple of response text and optional keyboard.
    """
    logger.info("Admin callback", extra={"callback_data": callback_data, "chat_id": chat_id})

    # Main menu buttons
    if callback_data == "newproject":
        return await _step_newproject_start(chat_id)
    elif callback_data == "listprojects":
        return await cmd_listprojects(pool), None
    elif callback_data == "help":
        return _cmd_help(), None
    elif callback_data == "settings":
        return "⚙️ **Настройки**\n\nЗдесь будет управление настройками аккаунта.", None
    
    # Help sub-buttons
    elif callback_data == "help_token":
        return _make_token_input_hint(), None
    
    # Project-specific buttons (format: action:project_id)
    elif callback_data.startswith("settoken:"):
        project_id = callback_data.split(":")[1]
        await _set_data(chat_id, {"project_id": project_id})
        await _set_state(chat_id, STATE_SETTOKEN_AWAIT_TOKEN)
        return _make_token_input_hint(), None
    elif callback_data.startswith("managers:"):
        project_id = callback_data.split(":")[1]
        return await cmd_listmanagers(project_id, pool), _make_project_keyboard(project_id)
    elif callback_data.startswith("knowledge:"):
        project_id = callback_data.split(":")[1]
        return (
            f"📚 **Загрузка знаний для проекта** `{project_id}`\n\n"
            f"📎 Отправьте файл (.txt, .pdf, .md) следующим сообщением.\n"
            f"📏 Макс. размер: 10 МБ, кодировка: UTF-8"
        ), None
    elif callback_data.startswith("promode:"):
        project_id = callback_data.split(":")[1]
        await _set_data(chat_id, {"project_id": project_id})
        await _set_state(chat_id, STATE_PROMODE_AWAIT_ENABLED)
        return "⚙️ **Pro-режим**\n\nВведите `on` для включения канваса или `off` для отключения.", None
    elif callback_data.startswith("delete:"):
        project_id = callback_data.split(":")[1]
        return (
            f"🗑️ **Удаление проекта** `{project_id}`\n\n"
            f"⚠️ Это действие НЕОБРАТИМО!\n"
            f"Все данные, боты и настройки будут удалены.\n\n"
            f"Для подтверждения отправьте: `DELETE {project_id}`"
        ), None
    
    # Template selection
    elif callback_data.startswith("tpl:"):
        return await _handle_template_selection(chat_id, callback_data, pool)
    
    # Unknown callback
    return "❌ Неизвестная команда. Используйте /help.", None

# =============================================================================
# CORE BUSINESS LOGIC (unchanged — only return type adapted)
# =============================================================================
async def _create_project_raw(name: str, pool) -> str:
    """
    Create a new project and return its ID (internal helper).
    
    Args:
        name: Project name.
        pool: Asyncpg connection pool.
    
    Returns:
        UUID string of the newly created project.
    """
    logger.info("Creating project", extra={"name": name})
    async with pool.acquire() as conn:
        project_id = await conn.fetchval("""
            INSERT INTO projects (id, name, owner_id, bot_token, system_prompt)
            VALUES (gen_random_uuid(), $1, 'admin', '', 'Ты — полезный AI-ассистент.')
            RETURNING id
        """, name)
    logger.info("Project created", extra={"project_id": project_id})
    return str(project_id)


async def cmd_newproject(name: str, pool) -> str:
    """Create project via command, return formatted response."""
    project_id = await _create_project_raw(name, pool)
    return (
        f"✅ Проект «{name}» создан.\n"
        f"🆔 ID: `{project_id}`\n\n"
        f"🔑 Следующий шаг: `/settoken {project_id} <токен>`"
    )


async def cmd_settoken(project_id: str, token: str, pool) -> str:
    """
    Set bot token for project and configure webhook.
    
    Args:
        project_id: Project UUID string.
        token: Bot token from BotFather.
        pool: Asyncpg connection pool.
    
    Returns:
        Confirmation message with webhook info.
    """
    logger.info("Setting token", extra={"project_id": project_id})
    secret_token = uuid.uuid4().hex
    
    project_repo = ProjectRepository(pool)
    try:
        await project_repo.set_bot_token(project_id, token)
        await project_repo.set_webhook_secret(project_id, secret_token)
    except Exception as e:
        logger.exception("Failed to set token", extra={"project_id": project_id, "error": str(e)})
        return f"❌ Ошибка: {str(e)}"
    
    base_url = settings.RENDER_EXTERNAL_URL or settings.PUBLIC_URL
    if not base_url:
        return "❌ PUBLIC_URL не настроен."
    
    webhook_url = f"{base_url.rstrip('/')}/webhook/{project_id}"
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/setWebhook",
                json={"url": webhook_url, "secret_token": secret_token}
            )
            if resp.status_code != 200:
                error = resp.json().get("description", f"HTTP {resp.status_code}") if resp.content else "Unknown"
                return f"❌ Вебхук не установлен: {error}"
            if not resp.json().get("ok"):
                return f"❌ Telegram error: {resp.json().get('description', 'unknown')}"
        except Exception as e:
            return f"❌ Ошибка API: {str(e)}"
    
    # Get bot username for nice link
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            username = resp.json()["result"]["username"] if resp.json().get("ok") else None
    except:
        username = None
    
    bot_link = f"https://t.me/{username}" if username else f"https://t.me/{project_id}"
    
    return (
        f"✅ Токен установлен! Вебхук: `{webhook_url}`\n\n"
        f"🤖 **Ваш бот**: {bot_link}\n"
        f"🔐 Секрет сохранён в базе."
    )


async def cmd_setmanager(project_id: str, manager_token: str, manager_chat_id: Optional[str], pool) -> str:
    """
    Set manager bot token and optionally add manager chat ID.
    
    Args:
        project_id: Project UUID string.
        manager_token: Manager bot token from BotFather.
        manager_chat_id: Optional Telegram chat ID of manager.
        pool: Asyncpg connection pool.
    
    Returns:
        Confirmation message.
    """
    logger.info("Setting manager", extra={"project_id": project_id})
    project_repo = ProjectRepository(pool)
    
    try:
        await project_repo.set_manager_bot_token(project_id, manager_token)
        if manager_chat_id:
            await project_repo.add_manager(project_id, manager_chat_id)
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"
    
    base_url = settings.RENDER_EXTERNAL_URL or settings.PUBLIC_URL
    webhook_url = f"{base_url.rstrip('/')}/manager/webhook"
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"https://api.telegram.org/bot{manager_token}/setWebhook",
                json={"url": webhook_url}
            )
            if not resp.json().get("ok"):
                return f"❌ Telegram: {resp.json().get('description', 'error')}"
        except Exception as e:
            return f"❌ Ошибка: {str(e)}"
    
    msg = f"✅ Менеджерский бот настроен!"
    if manager_chat_id:
        msg += f"\n👤 Менеджер `{manager_chat_id}` добавлен."
    return msg


async def cmd_listmanagers(project_id: str, pool) -> str:
    """Return formatted list of managers for a project."""
    managers = await ProjectRepository(pool).get_managers(project_id)
    if not managers:
        return f"📭 Для проекта `{project_id}` нет менеджеров."
    lines = [f"👥 **Менеджеры проекта** `{project_id}`:"]
    for i, cid in enumerate(managers, 1):
        lines.append(f"{i}. `{cid}`")
    return "\n".join(lines)


async def cmd_removemanager(project_id: str, manager_chat_id: str, pool) -> str:
    """Remove manager from project, return confirmation."""
    try:
        await ProjectRepository(pool).remove_manager(project_id, manager_chat_id)
        return f"✅ Менеджер `{manager_chat_id}` удалён."
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"


async def cmd_listprojects(pool) -> str:
    """List all projects with status indicators."""
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, name, bot_token, manager_bot_token, template_slug, is_pro_mode, created_at
            FROM projects ORDER BY created_at DESC
        """)
    if not rows:
        return "📭 Проектов пока нет."
    
    lines = ["📦 **Ваши проекты**:"]
    for r in rows:
        status = []
        if r['bot_token']: status.append("🔑")
        if r['manager_bot_token']: status.append("👥")
        if r['template_slug']: status.append(f"📦{r['template_slug']}")
        if r['is_pro_mode']: status.append("⭐Pro")
        
        date = r['created_at'].strftime("%d.%m") if r['created_at'] else "?"
        lines.append(f"• `{r['id']}` — {r['name']} {' '.join(status)} | {date}")
    
    return "\n".join(lines)


async def cmd_set_pro_mode(project_id: str, enabled: bool, pool) -> str:
    """Enable or disable Pro mode for a project."""
    try:
        await ProjectRepository(pool).set_pro_mode(project_id, enabled)
        status = "✅ включён" if enabled else "❌ отключён"
        extra = "🎨 Канвас доступен!" if enabled else "⚙️ Используются шаблоны."
        return f"✅ Pro-режим для `{project_id}` {status}.\n{extra}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"
