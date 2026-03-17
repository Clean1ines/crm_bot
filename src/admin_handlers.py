"""
Admin command handlers for managing projects via Telegram.

Supports both command-based and interactive step-by-step flows using Redis for state.
Provides wizard-style onboarding for project creation, token setup, and manager configuration.
"""

import uuid
import httpx
import asyncpg
import json
from typing import Optional, Dict, Any, List

from src.database.repositories.project_repository import ProjectRepository
from src.database.repositories.template_repository import TemplateRepository
from src.core.logging import get_logger
from src.core.config import settings
from src.services.redis_client import get_redis_client

logger = get_logger(__name__)

# Redis key prefixes for state management
STATE_PREFIX = "admin_state:"
DATA_PREFIX = "admin_data:"

# State constants for interactive flows
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

# ----------------------------------------------------------------------
# Redis helpers for state management
# ----------------------------------------------------------------------
async def _get_state(chat_id: str) -> str:
    """
    Retrieve current state for a given chat_id.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
    
    Returns:
        str: Current state string or STATE_IDLE if none set.
    """
    redis = await get_redis_client()
    state = await redis.get(f"{STATE_PREFIX}{chat_id}")
    return state.decode() if state and isinstance(state, bytes) else (state or STATE_IDLE)


async def _set_state(chat_id: str, state: str):
    """
    Set current state for a chat_id with TTL.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
        state: New state string to set.
    """
    redis = await get_redis_client()
    await redis.setex(f"{STATE_PREFIX}{chat_id}", 600, state)  # 10 min TTL
    logger.debug("State set", extra={"chat_id": chat_id, "state": state})


async def _clear_state(chat_id: str):
    """
    Clear state and data for a chat_id.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
    """
    redis = await get_redis_client()
    await redis.delete(f"{STATE_PREFIX}{chat_id}")
    await redis.delete(f"{DATA_PREFIX}{chat_id}")
    logger.debug("State cleared", extra={"chat_id": chat_id})


async def _get_data(chat_id: str) -> Dict[str, Any]:
    """
    Retrieve data associated with current state.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
    
    Returns:
        Dict[str, Any]: Stored data dict or empty dict if none.
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
    Store data associated with current state.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
        data: Dict to store as JSON.
    """
    redis = await get_redis_client()
    await redis.setex(f"{DATA_PREFIX}{chat_id}", 600, json.dumps(data))
    logger.debug("Data stored", extra={"chat_id": chat_id, "data_keys": list(data.keys())})


# ----------------------------------------------------------------------
# Command handlers (direct commands)
# ----------------------------------------------------------------------
async def handle_admin_command(text: str, pool) -> str:
    """
    Parse admin command and return response text.
    
    Args:
        text: Full message text from admin.
        pool: Asyncpg connection pool.
    
    Returns:
        str: Response text to send back to admin.
    """
    parts = text.strip().split()
    if not parts:
        return "Пустая команда."

    cmd = parts[0].lower()
    logger.info("Admin command received", extra={"cmd": cmd, "args": parts[1:]})

    if cmd == "/start":
        return await _cmd_start()
    elif cmd == "/help":
        return _cmd_help()
    elif cmd == "/newproject":
        if len(parts) < 2:
            return "Использование: /newproject <название>"
        name = " ".join(parts[1:])
        return await cmd_newproject(name, pool)
    elif cmd == "/settoken":
        if len(parts) != 3:
            return "Использование: /settoken <project_id> <bot_token>"
        project_id = parts[1]
        token = parts[2]
        return await cmd_settoken(project_id, token, pool)
    elif cmd == "/setmanager":
        if len(parts) < 3:
            return "Использование: /setmanager <project_id> <manager_token> [manager_chat_id]"
        project_id = parts[1]
        manager_token = parts[2]
        manager_chat_id = parts[3] if len(parts) > 3 else None
        return await cmd_setmanager(project_id, manager_token, manager_chat_id, pool)
    elif cmd == "/listmanagers":
        if len(parts) != 2:
            return "Использование: /listmanagers <project_id>"
        project_id = parts[1]
        return await cmd_listmanagers(project_id, pool)
    elif cmd == "/removemanager":
        if len(parts) != 3:
            return "Использование: /removemanager <project_id> <manager_chat_id>"
        project_id = parts[1]
        manager_chat_id = parts[2]
        return await cmd_removemanager(project_id, manager_chat_id, pool)
    elif cmd == "/listprojects":
        return await cmd_listprojects(pool)
    elif cmd == "/promode":
        if len(parts) != 3:
            return "Использование: /promode <project_id> <on|off>"
        project_id = parts[1]
        enabled = parts[2].lower() in ("on", "true", "1", "yes")
        return await cmd_set_pro_mode(project_id, enabled, pool)
    else:
        # Unknown command – maybe it's a step in a flow?
        return await _process_admin_step(text, None, pool)


async def _cmd_start() -> str:
    """
    Return welcome message with instructions and inline keyboard markup.
    
    Returns:
        str: Welcome message text with setup instructions.
    """
    return (
        "👋 Администратор фабрики ботов опознан!\n\n"
        "Я помогу вам управлять проектами. Вы можете использовать команды или кнопки ниже.\n\n"
        "📌 **Как получить токен бота?**\n"
        "1. Напишите @BotFather, создайте нового бота командой /newbot\n"
        "2. Скопируйте полученный токен (вида 123456:ABCdef...)\n"
        "3. Используйте его в команде /settoken или в диалоге с кнопками.\n\n"
        "📌 **Как получить ID менеджера?**\n"
        "1. Перейдите к боту @echoManagersBot и нажмите /start\n"
        "2. Бот пришлёт ваш chat_id (число). Скопируйте его.\n"
        "3. Используйте в команде /setmanager или в диалоге.\n\n"
        "Используйте кнопки ниже для пошаговой настройки:"
    )


def _cmd_help() -> str:
    """
    Return help message with available commands.
    
    Returns:
        str: Help text listing all admin commands.
    """
    return (
        "Доступные команды:\n"
        "/start – приветствие и инструкции\n"
        "/newproject <название> – создать новый проект\n"
        "/settoken <project_id> <токен> – привязать токен бота к проекту\n"
        "/setmanager <project_id> <manager_token> [chat_id] – настроить менеджерского бота\n"
        "/listmanagers <project_id> – список менеджеров проекта\n"
        "/removemanager <project_id> <chat_id> – удалить менеджера из проекта\n"
        "/listprojects – список всех проектов с базовой информацией\n"
        "/promode <project_id> <on|off> – включить/отключить Pro режим для проекта"
    )


# ----------------------------------------------------------------------
# Interactive step handling (called from webhook when message is not a command)
# ----------------------------------------------------------------------
async def handle_admin_step(chat_id: str, text: str, pool) -> Optional[str]:
    """
    Process a non-command message as part of an interactive flow.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
        text: Message text from admin.
        pool: Asyncpg connection pool.
    
    Returns:
        Optional[str]: Response text if flow is active, None otherwise.
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
) -> str:
    """
    Process one step of an interactive flow.
    
    Args:
        text: User input text.
        data: Stored step data dict.
        pool: Asyncpg connection pool.
        chat_id: Telegram chat ID (optional for logging).
        state: Current state string (optional for logging).
    
    Returns:
        str: Response text for the current step.
    """
    if chat_id is None or state is None:
        return "Неизвестная команда. Используйте /start для списка команд."

    logger.debug(
        "Processing admin step",
        extra={"chat_id": chat_id, "state": state, "text_preview": text[:50]}
    )

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
        return await _step_listmanagers_project(chat_id, text, pool)
    elif state == STATE_PROMODE_AWAIT_PROJECT:
        return await _step_promode_project(chat_id, text, pool)
    elif state == STATE_PROMODE_AWAIT_ENABLED:
        return await _step_promode_enabled(chat_id, text, pool)
    else:
        await _clear_state(chat_id)
        return "Неизвестное состояние. Диалог сброшен. Используйте /start для начала."


# ----------------------------------------------------------------------
# Step implementations (each returns response and may update state)
# ----------------------------------------------------------------------
async def _step_newproject_start(chat_id: str) -> str:
    """
    Start new project flow: ask for project name.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
    
    Returns:
        str: Prompt message asking for project name.
    """
    await _set_state(chat_id, STATE_NEWPROJECT_AWAIT_NAME)
    return "Введите название нового проекта:"


async def _step_newproject_name(chat_id: str, name: str, pool) -> str:
    """
    Process project name and create project, then ask for template.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
        name: Project name from user input.
        pool: Asyncpg connection pool.
    
    Returns:
        str: Response with project ID and template selection prompt.
    """
    # Create project first
    project_id = await _create_project_raw(name, pool)
    
    # Store project_id for next step
    await _set_data(chat_id, {"project_id": project_id})
    
    # Move to template selection
    await _set_state(chat_id, STATE_NEWPROJECT_AWAIT_TEMPLATE)
    
    return (
        f"✅ Проект «{name}» создан.\nID: `{project_id}`\n\n"
        "Выберите шаблон для настройки бота:\n"
        "• `support` – Поддержка клиентов (ответы на вопросы + эскалация)\n"
        "• `leads` – Генерация лидов (сбор контактов + CRM)\n"
        "• `orders` – Приём заказов (меню + оформление)\n"
        "• `custom` – Пустой шаблон для ручной настройки в канвасе (Pro режим)\n"
        "\nВведите slug шаблона или `skip` для пропуска:"
    )


async def _handle_template_selection(chat_id: str, template_slug: str, pool) -> str:
    """
    Handle template selection after project creation.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
        template_slug: Selected template slug or 'skip'.
        pool: Asyncpg connection pool.
    
    Returns:
        str: Confirmation message with next steps.
    """
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    
    if not project_id:
        await _clear_state(chat_id)
        return "❌ Ошибка: данные о проекте утеряны. Начните создание проекта заново."
    
    # Handle skip or custom template
    if template_slug.lower() in ("skip", "custom", "none", ""):
        await _clear_state(chat_id)
        return (
            f"✅ Проект {project_id} создан без шаблона.\n"
            "Теперь установите токен бота командой:\n"
            f"`/settoken {project_id} <ваш_токен>`\n"
            "\n💡 Совет: Для доступа к визуальному конструктору включите Pro режим:\n"
            f"`/promode {project_id} on`"
        )
    
    # Validate and apply template
    template_repo = TemplateRepository(pool)
    template = await template_repo.get_by_slug(template_slug)
    
    if not template:
        return (
            f"❌ Шаблон «{template_slug}» не найден.\n"
            "Доступные шаблоны: `support`, `leads`, `orders`, `custom`\n"
            "Введите правильный slug или `skip` для пропуска:"
        )
    
    # Apply template to project
    project_repo = ProjectRepository(pool)
    success = await project_repo.apply_template(project_id, template_slug)
    
    if not success:
        await _clear_state(chat_id)
        return f"❌ Не удалось применить шаблон. Попробуйте ещё раз или используйте `skip`."
    
    await _clear_state(chat_id)
    
    return (
        f"✅ Шаблон «{template['name']}» применён к проекту {project_id}.\n"
        f"📝 Описание: {template['description']}\n\n"
        "Теперь установите токен бота:\n"
        f"`/settoken {project_id} <ваш_токен>`\n"
        "\nПосле установки токена бот будет готов к работе!"
    )


async def _step_settoken_start(chat_id: str) -> str:
    """
    Start set token flow: ask for project ID.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
    
    Returns:
        str: Prompt message asking for project ID.
    """
    await _set_state(chat_id, STATE_SETTOKEN_AWAIT_PROJECT)
    return "Введите ID проекта (можно получить через /listprojects):"


async def _step_settoken_project(chat_id: str, project_id: str, pool) -> str:
    """
    Store project ID and ask for token.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
        project_id: Project UUID from user input.
        pool: Asyncpg connection pool.
    
    Returns:
        str: Prompt for bot token or error if project not found.
    """
    # Validate project exists
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM projects WHERE id = $1", 
            uuid.UUID(project_id)
        )
        if not exists:
            return f"❌ Проект с ID {project_id} не найден. Попробуйте ещё раз."
    
    await _set_data(chat_id, {"project_id": project_id})
    await _set_state(chat_id, STATE_SETTOKEN_AWAIT_TOKEN)
    return "Введите токен бота для этого проекта:"


async def _step_settoken_token(chat_id: str, token: str, pool) -> str:
    """
    Set token for the project.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
        token: Bot token from user input.
        pool: Asyncpg connection pool.
    
    Returns:
        str: Confirmation message with webhook info.
    """
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    
    if not project_id:
        await _clear_state(chat_id)
        return "Ошибка: данные о проекте утеряны. Начните заново."
    
    result = await cmd_settoken(project_id, token, pool)
    await _clear_state(chat_id)
    return result


async def _step_setmanager_start(chat_id: str) -> str:
    """
    Start set manager flow: ask for project ID.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
    
    Returns:
        str: Prompt message asking for project ID.
    """
    await _set_state(chat_id, STATE_SETMANAGER_AWAIT_PROJECT)
    return "Введите ID проекта (можно получить через /listprojects):"


async def _step_setmanager_project(chat_id: str, project_id: str, pool) -> str:
    """
    Store project ID and ask for manager bot token.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
        project_id: Project UUID from user input.
        pool: Asyncpg connection pool.
    
    Returns:
        str: Prompt for manager bot token or error if project not found.
    """
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM projects WHERE id = $1", 
            uuid.UUID(project_id)
        )
        if not exists:
            return f"❌ Проект с ID {project_id} не найден. Попробуйте ещё раз."
    
    await _set_data(chat_id, {"project_id": project_id})
    await _set_state(chat_id, STATE_SETMANAGER_AWAIT_TOKEN)
    return "Введите токен менеджерского бота (создайте его через @BotFather):"


async def _step_setmanager_token(chat_id: str, manager_token: str, pool) -> str:
    """
    Store manager token and ask for manager chat ID.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
        manager_token: Manager bot token from user input.
        pool: Asyncpg connection pool.
    
    Returns:
        str: Prompt for manager chat ID.
    """
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    
    if not project_id:
        await _clear_state(chat_id)
        return "Ошибка: данные о проекте утеряны. Начните заново."
    
    await _set_data(chat_id, {"project_id": project_id, "manager_token": manager_token})
    await _set_state(chat_id, STATE_SETMANAGER_AWAIT_CHAT_ID)
    return "Введите chat_id менеджера (получите у бота @echoManagersBot):"


async def _step_setmanager_chat_id(chat_id: str, manager_chat_id: str, pool) -> str:
    """
    Set manager token and add manager chat ID.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
        manager_chat_id: Telegram chat ID of the manager.
        pool: Asyncpg connection pool.
    
    Returns:
        str: Confirmation message.
    """
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    manager_token = data.get("manager_token")
    
    if not project_id or not manager_token:
        await _clear_state(chat_id)
        return "Ошибка: данные утеряны. Начните заново."
    
    result = await cmd_setmanager(project_id, manager_token, manager_chat_id, pool)
    await _clear_state(chat_id)
    return result


async def _step_listmanagers_project(chat_id: str, project_id: str, pool) -> str:
    """
    Show managers for a given project ID.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
        project_id: Project UUID from user input.
        pool: Asyncpg connection pool.
    
    Returns:
        str: List of managers or error message.
    """
    result = await cmd_listmanagers(project_id, pool)
    await _clear_state(chat_id)
    return result


async def _step_promode_start(chat_id: str) -> str:
    """
    Start Pro mode toggle flow: ask for project ID.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
    
    Returns:
        str: Prompt message asking for project ID.
    """
    await _set_state(chat_id, STATE_PROMODE_AWAIT_PROJECT)
    return "Введите ID проекта для изменения Pro режима:"


async def _step_promode_project(chat_id: str, project_id: str, pool) -> str:
    """
    Store project ID and ask for enabled/disabled.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
        project_id: Project UUID from user input.
        pool: Asyncpg connection pool.
    
    Returns:
        str: Prompt for on/off or error if project not found.
    """
    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT 1 FROM projects WHERE id = $1", 
            uuid.UUID(project_id)
        )
        if not exists:
            return f"❌ Проект с ID {project_id} не найден. Попробуйте ещё раз."
    
    await _set_data(chat_id, {"project_id": project_id})
    await _set_state(chat_id, STATE_PROMODE_AWAIT_ENABLED)
    return "Введите `on` для включения Pro режима или `off` для отключения:"


async def _step_promode_enabled(chat_id: str, value: str, pool) -> str:
    """
    Set Pro mode enabled/disabled for project.
    
    Args:
        chat_id: Telegram chat ID of the admin user.
        value: "on"/"off" string from user input.
        pool: Asyncpg connection pool.
    
    Returns:
        str: Confirmation message.
    """
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    
    if not project_id:
        await _clear_state(chat_id)
        return "Ошибка: данные о проекте утеряны. Начните заново."
    
    enabled = value.lower() in ("on", "true", "1", "yes", "enable", "enabled")
    result = await cmd_set_pro_mode(project_id, enabled, pool)
    await _clear_state(chat_id)
    return result


# ----------------------------------------------------------------------
# Callback handler for inline buttons
# ----------------------------------------------------------------------
async def handle_admin_callback(callback_data: str, chat_id: str, pool) -> str:
    """
    Handle callback queries from inline buttons.
    
    Args:
        callback_data: Callback data string from button press.
        chat_id: Telegram chat ID of the admin user.
        pool: Asyncpg connection pool.
    
    Returns:
        str: Text response to send as new message.
    """
    logger.info(
        "Admin callback received",
        extra={"callback_data": callback_data, "chat_id": chat_id}
    )

    if callback_data == "newproject":
        return await _step_newproject_start(chat_id)
    elif callback_data == "settoken":
        return await _step_settoken_start(chat_id)
    elif callback_data == "setmanager":
        return await _step_setmanager_start(chat_id)
    elif callback_data == "promode":
        return await _step_promode_start(chat_id)
    elif callback_data == "listprojects":
        return await cmd_listprojects(pool)
    elif callback_data == "listmanagers":
        await _set_state(chat_id, STATE_LISTMANAGERS_AWAIT_PROJECT)
        return "Введите ID проекта для просмотра менеджеров:"
    elif callback_data == "help":
        return _cmd_help()
    else:
        return "Неизвестная команда. Используйте /help для списка команд."


# ----------------------------------------------------------------------
# Core command implementations (reused by steps and direct commands)
# ----------------------------------------------------------------------
async def _create_project_raw(name: str, pool) -> str:
    """
    Create a new project and return its ID.
    
    Internal helper that doesn't format response text.
    
    Args:
        name: Project name.
        pool: Asyncpg connection pool.
    
    Returns:
        str: UUID of the newly created project.
    """
    logger.info("Creating new project", extra={"name": name})
    async with pool.acquire() as conn:
        project_id = await conn.fetchval("""
            INSERT INTO projects (id, name, owner_id, bot_token, system_prompt)
            VALUES (gen_random_uuid(), $1, 'admin', '', 'Ты — полезный AI-ассистент.')
            RETURNING id
        """, name)
    logger.info("Project created", extra={"project_id": project_id, "name": name})
    return str(project_id)


async def cmd_newproject(name: str, pool) -> str:
    """
    Create a new project, return its ID with formatted response.
    
    Args:
        name: Project name from command.
        pool: Asyncpg connection pool.
    
    Returns:
        str: Formatted response with project ID and next steps.
    """
    project_id = await _create_project_raw(name, pool)
    return (
        f"✅ Проект «{name}» создан.\nID: `{project_id}`\n"
        f"Теперь установите токен командой: `/settoken {project_id} <токен>`"
    )


async def cmd_settoken(project_id: str, token: str, pool) -> str:
    """
    Set bot token for project and set webhook with secret token.
    
    Args:
        project_id: Project UUID string.
        token: Bot token from BotFather.
        pool: Asyncpg connection pool.
    
    Returns:
        str: Confirmation message with webhook info.
    """
    logger.info("Setting token for project", extra={"project_id": project_id})

    # Generate a random secret token for webhook verification
    secret_token = uuid.uuid4().hex
    logger.debug("Generated webhook secret", extra={"project_id": project_id})

    # Store the secret in the database
    project_repo = ProjectRepository(pool)
    try:
        await project_repo.set_bot_token(project_id, token)
        await project_repo.set_webhook_secret(project_id, secret_token)
    except Exception as e:
        logger.exception(
            "Failed to set bot token or secret",
            extra={"project_id": project_id, "error": str(e)}
        )
        return f"❌ Не удалось сохранить токен или секрет: {str(e)}"

    base_url = settings.RENDER_EXTERNAL_URL or settings.PUBLIC_URL
    if not base_url:
        logger.error("Public URL not configured")
        return "❌ Не удалось определить публичный URL сервиса. Убедитесь, что переменная RENDER_EXTERNAL_URL или PUBLIC_URL задана."

    webhook_url = f"{base_url.rstrip('/')}/webhook/{project_id}"
    api_url = f"https://api.telegram.org/bot{token}/setWebhook"
    payload = {
        "url": webhook_url,
        "secret_token": secret_token
    }

    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(api_url, json=payload)
            if resp.status_code != 200:
                error_detail = "неизвестная ошибка"
                try:
                    error_data = resp.json()
                    error_detail = error_data.get("description", str(resp.status_code))
                except Exception:
                    error_detail = f"HTTP {resp.status_code}"
                logger.error(
                    "Failed to set webhook",
                    extra={"project_id": project_id, "error": error_detail}
                )
                return f"❌ Токен сохранён, но не удалось установить вебхук: {error_detail}"
            
            data = resp.json()
            if data.get("ok"):
                logger.info(
                    "Webhook set successfully",
                    extra={"project_id": project_id, "webhook_url": webhook_url}
                )
                return (
                    f"✅ Токен для проекта {project_id} успешно обновлён и вебхук установлен.\n"
                    f"URL: `{webhook_url}`\n"
                    f"Секретный токен сохранён в базе."
                )
            else:
                error_msg = data.get('description', 'неизвестно')
                logger.error(
                    "Telegram API error",
                    extra={"project_id": project_id, "error": error_msg}
                )
                return f"❌ Токен сохранён, но Telegram вернул ошибку: {error_msg}"
        
        except Exception as e:
            logger.exception(
                "Exception while setting webhook",
                extra={"project_id": project_id, "error": str(e)}
            )
            return f"❌ Токен сохранён, но произошла ошибка при вызове Telegram API: {str(e)}"


async def cmd_setmanager(
    project_id: str, 
    manager_token: str, 
    manager_chat_id: Optional[str], 
    pool
) -> str:
    """
    Set manager bot token and optionally add manager chat ID.
    
    Args:
        project_id: Project UUID string.
        manager_token: Manager bot token from BotFather.
        manager_chat_id: Optional Telegram chat ID of manager.
        pool: Asyncpg connection pool.
    
    Returns:
        str: Confirmation message.
    """
    logger.info(
        "Setting manager bot token",
        extra={"project_id": project_id, "has_chat_id": bool(manager_chat_id)}
    )
    
    project_repo = ProjectRepository(pool)
    try:
        await project_repo.set_manager_bot_token(project_id, manager_token)
    except Exception as e:
        logger.exception(
            "Failed to set manager bot token",
            extra={"project_id": project_id, "error": str(e)}
        )
        return f"❌ Не удалось сохранить токен: {str(e)}"

    if manager_chat_id:
        try:
            await project_repo.add_manager(project_id, manager_chat_id)
        except Exception as e:
            logger.exception(
                "Failed to add manager",
                extra={"project_id": project_id, "manager_chat_id": manager_chat_id, "error": str(e)}
            )
            return f"❌ Токен сохранён, но не удалось добавить менеджера: {str(e)}"

    base_url = settings.RENDER_EXTERNAL_URL or settings.PUBLIC_URL
    if not base_url:
        logger.error("Public URL not configured")
        return "❌ Не удалось определить публичный URL сервиса."

    webhook_url = f"{base_url.rstrip('/')}/manager/webhook"
    api_url = f"https://api.telegram.org/bot{manager_token}/setWebhook"
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(api_url, json={"url": webhook_url})
            if resp.status_code != 200:
                error_detail = "неизвестная ошибка"
                try:
                    error_data = resp.json()
                    error_detail = error_data.get("description", str(resp.status_code))
                except Exception:
                    error_detail = f"HTTP {resp.status_code}"
                logger.error(
                    "Failed to set manager webhook",
                    extra={"project_id": project_id, "error": error_detail}
                )
                return f"❌ Токен сохранён, но не удалось установить вебхук менеджерского бота: {error_detail}"
            
            data = resp.json()
            if data.get("ok"):
                logger.info(
                    "Manager webhook set",
                    extra={"project_id": project_id, "webhook_url": webhook_url}
                )
                msg = f"✅ Токен менеджерского бота для проекта {project_id} успешно обновлён."
                if manager_chat_id:
                    msg += f"\nМенеджер {manager_chat_id} добавлен."
                return msg
            else:
                error_msg = data.get('description', 'неизвестно')
                logger.error(
                    "Telegram API error for manager bot",
                    extra={"project_id": project_id, "error": error_msg}
                )
                return f"❌ Токен сохранён, но Telegram вернул ошибку: {error_msg}"
        
        except Exception as e:
            logger.exception(
                "Exception while setting manager webhook",
                extra={"project_id": project_id, "error": str(e)}
            )
            return f"❌ Токен сохранён, но произошла ошибка при вызове Telegram API: {str(e)}"


async def cmd_listmanagers(project_id: str, pool) -> str:
    """
    Return list of managers for a project.
    
    Args:
        project_id: Project UUID string.
        pool: Asyncpg connection pool.
    
    Returns:
        str: Formatted list of managers or message if none.
    """
    logger.info("Listing managers", extra={"project_id": project_id})
    
    project_repo = ProjectRepository(pool)
    managers = await project_repo.get_managers(project_id)
    
    if not managers:
        return f"Для проекта {project_id} нет менеджеров."
    
    lines = [f"📋 Менеджеры проекта {project_id}:"]
    for i, chat_id in enumerate(managers, 1):
        lines.append(f"{i}. `{chat_id}`")
    
    return "\n".join(lines)


async def cmd_removemanager(project_id: str, manager_chat_id: str, pool) -> str:
    """
    Remove a manager from project.
    
    Args:
        project_id: Project UUID string.
        manager_chat_id: Telegram chat ID to remove.
        pool: Asyncpg connection pool.
    
    Returns:
        str: Confirmation or error message.
    """
    logger.info(
        "Removing manager",
        extra={"project_id": project_id, "manager_chat_id": manager_chat_id}
    )
    
    project_repo = ProjectRepository(pool)
    try:
        await project_repo.remove_manager(project_id, manager_chat_id)
    except Exception as e:
        logger.exception(
            "Failed to remove manager",
            extra={"project_id": project_id, "manager_chat_id": manager_chat_id, "error": str(e)}
        )
        return f"❌ Ошибка при удалении менеджера: {str(e)}"
    
    return f"✅ Менеджер `{manager_chat_id}` удалён из проекта {project_id}."


async def cmd_listprojects(pool) -> str:
    """
    List all projects with basic info.
    
    Args:
        pool: Asyncpg connection pool.
    
    Returns:
        str: Formatted list of projects.
    """
    logger.info("Listing all projects")
    
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, name, bot_token, manager_bot_token, template_slug, is_pro_mode, created_at
            FROM projects 
            ORDER BY created_at DESC
        """)
    
    if not rows:
        return "Проектов пока нет."
    
    lines = ["📋 Список проектов:"]
    for r in rows:
        token_part = "🔐" if r['bot_token'] else "⚪"
        manager_part = " 👥" if r['manager_bot_token'] else ""
        template_part = f" 📦{r['template_slug']}" if r['template_slug'] else ""
        pro_part = " ⭐Pro" if r['is_pro_mode'] else ""
        created = r['created_at'].strftime("%Y-%m-%d") if r['created_at'] else "?"
        
        lines.append(
            f"• `{r['id']}` – {r['name']}\n"
            f"  {token_part}{manager_part}{template_part}{pro_part} | {created}"
        )
    
    return "\n".join(lines)


async def cmd_set_pro_mode(project_id: str, enabled: bool, pool) -> str:
    """
    Enable or disable Pro mode for a project.
    
    Pro mode grants access to custom workflow canvas and advanced features.
    
    Args:
        project_id: Project UUID string.
        enabled: True to enable, False to disable.
        pool: Asyncpg connection pool.
    
    Returns:
        str: Confirmation message.
    """
    logger.info(
        "Setting Pro mode",
        extra={"project_id": project_id, "enabled": enabled}
    )
    
    project_repo = ProjectRepository(pool)
    try:
        await project_repo.set_pro_mode(project_id, enabled)
    except Exception as e:
        logger.exception(
            "Failed to set Pro mode",
            extra={"project_id": project_id, "enabled": enabled, "error": str(e)}
        )
        return f"❌ Не удалось изменить режим: {str(e)}"
    
    status = "включён" if enabled else "отключён"
    return (
        f"✅ Pro режим для проекта {project_id} {status}.\n"
        f"{'🎨 Теперь доступен визуальный конструктор в веб-интерфейсе.' if enabled else '⚙️ Проект использует стандартные шаблоны.'}"
    )
