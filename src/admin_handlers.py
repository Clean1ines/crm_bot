"""
Admin command handlers for managing projects via Telegram.
Supports both command-based and interactive step-by-step flows using Redis for state.
"""

import uuid
import httpx
import asyncpg
import json
from typing import Optional, Dict, Any
from src.database.repositories.project_repository import ProjectRepository
from src.core.logging import get_logger
from src.core.config import settings
from src.services.redis_client import get_redis_client

logger = get_logger(__name__)

# Redis key prefixes for state management
STATE_PREFIX = "admin_state:"
DATA_PREFIX = "admin_data:"

# State constants
STATE_IDLE = "idle"
STATE_NEWPROJECT_AWAIT_NAME = "newproject:await_name"
STATE_SETTOKEN_AWAIT_PROJECT = "settoken:await_project"
STATE_SETTOKEN_AWAIT_TOKEN = "settoken:await_token"
STATE_SETMANAGER_AWAIT_PROJECT = "setmanager:await_project"
STATE_SETMANAGER_AWAIT_TOKEN = "setmanager:await_token"
STATE_SETMANAGER_AWAIT_CHAT_ID = "setmanager:await_chat_id"

# ----------------------------------------------------------------------
# Redis helpers
# ----------------------------------------------------------------------
async def _get_state(chat_id: str) -> str:
    """Retrieve current state for a given chat_id."""
    redis = await get_redis_client()
    state = await redis.get(f"{STATE_PREFIX}{chat_id}")
    return state if state else STATE_IDLE

async def _set_state(chat_id: str, state: str):
    """Set current state for a chat_id."""
    redis = await get_redis_client()
    await redis.setex(f"{STATE_PREFIX}{chat_id}", 600, state)  # 10 min TTL

async def _clear_state(chat_id: str):
    """Clear state and data for a chat_id."""
    redis = await get_redis_client()
    await redis.delete(f"{STATE_PREFIX}{chat_id}")
    await redis.delete(f"{DATA_PREFIX}{chat_id}")

async def _get_data(chat_id: str) -> Dict[str, Any]:
    """Retrieve data associated with current state."""
    redis = await get_redis_client()
    data = await redis.get(f"{DATA_PREFIX}{chat_id}")
    return json.loads(data) if data else {}

async def _set_data(chat_id: str, data: Dict[str, Any]):
    """Store data associated with current state."""
    redis = await get_redis_client()
    await redis.setex(f"{DATA_PREFIX}{chat_id}", 600, json.dumps(data))

# ----------------------------------------------------------------------
# Command handlers (direct commands)
# ----------------------------------------------------------------------
async def handle_admin_command(text: str, pool) -> str:
    """Parse admin command and return response text."""
    parts = text.strip().split()
    if not parts:
        return "Пустая команда."

    cmd = parts[0].lower()
    logger.info(f"Admin command received: {cmd}", extra={"args": parts[1:]})

    if cmd == "/start":
        return await _cmd_start()
    elif cmd == "/help":
        return await _cmd_help()
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
    else:
        # Unknown command – maybe it's a step in a flow?
        # Will be handled by the step processor.
        return await _process_admin_step(text, None, pool)

async def _cmd_start() -> str:
    """Return welcome message with instructions and inline keyboard markup."""
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
    return (
        "Доступные команды:\n"
        "/start – приветствие и инструкции\n"
        "/newproject <название> – создать новый проект\n"
        "/settoken <project_id> <токен> – привязать токен\n"
        "/setmanager <project_id> <manager_token> [manager_chat_id] – настроить менеджера\n"
        "/listmanagers <project_id> – список менеджеров\n"
        "/removemanager <project_id> <manager_chat_id> – удалить менеджера\n"
        "/listprojects – список проектов"
    )

# ----------------------------------------------------------------------
# Interactive step handling (called from webhook when a message is not a command)
# ----------------------------------------------------------------------
async def handle_admin_step(chat_id: str, text: str, pool) -> Optional[str]:
    """
    Process a non-command message as part of an interactive flow.
    Returns response text or None if no flow active.
    """
    state = await _get_state(chat_id)
    if state == STATE_IDLE:
        return None

    data = await _get_data(chat_id)
    return await _process_admin_step(text, data, pool, chat_id, state)

async def _process_admin_step(text: str, data: Dict[str, Any], pool, chat_id: Optional[str] = None, state: Optional[str] = None) -> str:
    """Process one step of an interactive flow."""
    if chat_id is None or state is None:
        # Called directly from command – no active flow
        return "Неизвестная команда. Используйте /start для списка команд."

    if state == STATE_NEWPROJECT_AWAIT_NAME:
        return await _step_newproject_name(chat_id, text, pool)
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
    else:
        await _clear_state(chat_id)
        return "Неизвестное состояние. Диалог сброшен."

# ----------------------------------------------------------------------
# Step implementations (each returns response and may update state)
# ----------------------------------------------------------------------
async def _step_newproject_start(chat_id: str) -> str:
    """Start new project flow: ask for project name."""
    await _set_state(chat_id, STATE_NEWPROJECT_AWAIT_NAME)
    return "Введите название нового проекта:"

async def _step_newproject_name(chat_id: str, name: str, pool) -> str:
    """Process project name and create project."""
    result = await cmd_newproject(name, pool)
    await _clear_state(chat_id)
    return result

async def _step_settoken_start(chat_id: str) -> str:
    """Start set token flow: ask for project ID."""
    await _set_state(chat_id, STATE_SETTOKEN_AWAIT_PROJECT)
    return "Введите ID проекта (можно получить через /listprojects):"

async def _step_settoken_project(chat_id: str, project_id: str, pool) -> str:
    """Store project ID and ask for token."""
    # Validate project exists
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM projects WHERE id = $1", uuid.UUID(project_id))
        if not exists:
            return f"❌ Проект с ID {project_id} не найден. Попробуйте ещё раз."
    await _set_data(chat_id, {"project_id": project_id})
    await _set_state(chat_id, STATE_SETTOKEN_AWAIT_TOKEN)
    return "Введите токен бота для этого проекта:"

async def _step_settoken_token(chat_id: str, token: str, pool) -> str:
    """Set token for the project."""
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    if not project_id:
        await _clear_state(chat_id)
        return "Ошибка: данные о проекте утеряны. Начните заново."
    result = await cmd_settoken(project_id, token, pool)
    await _clear_state(chat_id)
    return result

async def _step_setmanager_start(chat_id: str) -> str:
    """Start set manager flow: ask for project ID."""
    await _set_state(chat_id, STATE_SETMANAGER_AWAIT_PROJECT)
    return "Введите ID проекта (можно получить через /listprojects):"

async def _step_setmanager_project(chat_id: str, project_id: str, pool) -> str:
    """Store project ID and ask for manager bot token."""
    async with pool.acquire() as conn:
        exists = await conn.fetchval("SELECT 1 FROM projects WHERE id = $1", uuid.UUID(project_id))
        if not exists:
            return f"❌ Проект с ID {project_id} не найден. Попробуйте ещё раз."
    await _set_data(chat_id, {"project_id": project_id})
    await _set_state(chat_id, STATE_SETMANAGER_AWAIT_TOKEN)
    return "Введите токен менеджерского бота (создайте его через @BotFather):"

async def _step_setmanager_token(chat_id: str, manager_token: str, pool) -> str:
    """Store manager token and ask for manager chat ID."""
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    if not project_id:
        await _clear_state(chat_id)
        return "Ошибка: данные о проекте утеряны. Начните заново."
    # Optionally validate token by calling getMe?
    await _set_data(chat_id, {"project_id": project_id, "manager_token": manager_token})
    await _set_state(chat_id, STATE_SETMANAGER_AWAIT_CHAT_ID)
    return "Введите chat_id менеджера (получите у бота @echoManagersBot):"

async def _step_setmanager_chat_id(chat_id: str, manager_chat_id: str, pool) -> str:
    """Set manager token and add manager chat ID."""
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    manager_token = data.get("manager_token")
    if not project_id or not manager_token:
        await _clear_state(chat_id)
        return "Ошибка: данные утеряны. Начните заново."
    result = await cmd_setmanager(project_id, manager_token, manager_chat_id, pool)
    await _clear_state(chat_id)
    return result

# ----------------------------------------------------------------------
# Callback handler for inline buttons
# ----------------------------------------------------------------------
async def handle_admin_callback(callback_data: str, chat_id: str, pool) -> str:
    """
    Handle callback queries from inline buttons.
    Returns text response that should be sent as a new message.
    """
    logger.info(f"Admin callback received: {callback_data} from {chat_id}")

    if callback_data == "newproject":
        return await _step_newproject_start(chat_id)
    elif callback_data == "settoken":
        return await _step_settoken_start(chat_id)
    elif callback_data == "setmanager":
        return await _step_setmanager_start(chat_id)
    elif callback_data == "listprojects":
        return await cmd_listprojects(pool)
    elif callback_data == "listmanagers":
        # Ask for project ID via step flow
        await _set_state(chat_id, STATE_LISTMANAGERS_AWAIT_PROJECT)
        return "Введите ID проекта для просмотра менеджеров:"
    elif callback_data == "help":
        return _cmd_help()
    else:
        return "Неизвестная команда."

# ----------------------------------------------------------------------
# Core command implementations (reused by steps and direct commands)
# ----------------------------------------------------------------------
async def cmd_newproject(name: str, pool) -> str:
    """Create a new project, return its ID."""
    logger.info(f"Creating new project with name: {name}")
    async with pool.acquire() as conn:
        project_repo = ProjectRepository(pool)
        project_id = await conn.fetchval("""
            INSERT INTO projects (id, name, owner_id, bot_token, system_prompt)
            VALUES (gen_random_uuid(), $1, 'admin', '', 'Ты — полезный AI-ассистент.')
            RETURNING id
        """, name)
    logger.info(f"Project created successfully: {project_id}")
    return f"✅ Проект «{name}» создан.\nID: {project_id}\nТеперь установи токен командой /settoken {project_id} <токен>"

async def cmd_settoken(project_id: str, token: str, pool) -> str:
    """Set bot token for project and set webhook."""
    logger.info(f"Setting token for project {project_id}")
    async with pool.acquire() as conn:
        result = await conn.execute("""
            UPDATE projects SET bot_token = $1 WHERE id = $2
        """, token, uuid.UUID(project_id))
        if result.split()[-1] == "0":
            logger.warning(f"Project {project_id} not found")
            return f"❌ Проект с ID {project_id} не найден."

    base_url = settings.RENDER_EXTERNAL_URL or settings.PUBLIC_URL
    if not base_url:
        logger.error("RENDER_EXTERNAL_URL or PUBLIC_URL not set")
        return "❌ Не удалось определить публичный URL сервиса. Убедитесь, что переменная RENDER_EXTERNAL_URL или PUBLIC_URL задана."

    webhook_url = f"{base_url.rstrip('/')}/webhook/{project_id}"
    api_url = f"https://api.telegram.org/bot{token}/setWebhook"
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
                logger.error(f"Failed to set webhook for project {project_id}: {error_detail}")
                return f"❌ Токен сохранён, но не удалось установить вебхук: {error_detail}"
            data = resp.json()
            if data.get("ok"):
                logger.info(f"Webhook set successfully for project {project_id} at {webhook_url}")
                return f"✅ Токен для проекта {project_id} успешно обновлён и вебхук установлен на {webhook_url}"
            else:
                error_msg = data.get('description', 'неизвестно')
                logger.error(f"Telegram API error for project {project_id}: {error_msg}")
                return f"❌ Токен сохранён, но Telegram вернул ошибку: {error_msg}"
        except Exception as e:
            logger.exception(f"Exception while setting webhook for project {project_id}")
            return f"❌ Токен сохранён, но произошла ошибка при вызове Telegram API: {str(e)}"

async def cmd_setmanager(project_id: str, manager_token: str, manager_chat_id: Optional[str], pool) -> str:
    """Set manager bot token and optionally add manager chat ID."""
    logger.info(f"Setting manager bot token for project {project_id}")
    project_repo = ProjectRepository(pool)
    try:
        await project_repo.set_manager_bot_token(project_id, manager_token)
    except Exception as e:
        logger.exception(f"Failed to set manager bot token for project {project_id}")
        return f"❌ Не удалось сохранить токен: {str(e)}"

    if manager_chat_id:
        try:
            await project_repo.add_manager(project_id, manager_chat_id)
        except Exception as e:
            logger.exception(f"Failed to add manager {manager_chat_id} to project {project_id}")
            return f"❌ Токен сохранён, но не удалось добавить менеджера: {str(e)}"

    base_url = settings.RENDER_EXTERNAL_URL or settings.PUBLIC_URL
    if not base_url:
        logger.error("RENDER_EXTERNAL_URL or PUBLIC_URL not set")
        return "❌ Не удалось определить публичный URL сервиса. Убедитесь, что переменная RENDER_EXTERNAL_URL или PUBLIC_URL задана."

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
                logger.error(f"Failed to set manager webhook for project {project_id}: {error_detail}")
                return f"❌ Токен сохранён, но не удалось установить вебхук менеджерского бота: {error_detail}"
            data = resp.json()
            if data.get("ok"):
                logger.info(f"Manager webhook set for project {project_id}")
                msg = f"✅ Токен менеджерского бота для проекта {project_id} успешно обновлён и вебхук установлен на {webhook_url}"
                if manager_chat_id:
                    msg += f"\nМенеджер {manager_chat_id} добавлен."
                return msg
            else:
                error_msg = data.get('description', 'неизвестно')
                logger.error(f"Telegram API error for manager bot: {error_msg}")
                return f"❌ Токен сохранён, но Telegram вернул ошибку: {error_msg}"
        except Exception as e:
            logger.exception(f"Exception while setting manager webhook for project {project_id}")
            return f"❌ Токен сохранён, но произошла ошибка при вызове Telegram API: {str(e)}"

async def cmd_listmanagers(project_id: str, pool) -> str:
    """Return list of managers for a project."""
    logger.info(f"Listing managers for project {project_id}")
    project_repo = ProjectRepository(pool)
    managers = await project_repo.get_managers(project_id)
    if not managers:
        return f"Для проекта {project_id} нет менеджеров."
    lines = [f"📋 Менеджеры проекта {project_id}:"]
    for i, chat_id in enumerate(managers, 1):
        lines.append(f"{i}. {chat_id}")
    return "\n".join(lines)

async def cmd_removemanager(project_id: str, manager_chat_id: str, pool) -> str:
    """Remove a manager from project."""
    logger.info(f"Removing manager {manager_chat_id} from project {project_id}")
    project_repo = ProjectRepository(pool)
    try:
        await project_repo.remove_manager(project_id, manager_chat_id)
    except Exception as e:
        logger.exception(f"Failed to remove manager {manager_chat_id} from project {project_id}")
        return f"❌ Ошибка при удалении менеджера: {str(e)}"
    return f"✅ Менеджер {manager_chat_id} удалён из проекта {project_id}."

async def cmd_listprojects(pool) -> str:
    """List all projects with basic info."""
    logger.info("Listing all projects")
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, name, bot_token, manager_bot_token FROM projects ORDER BY created_at DESC")
    if not rows:
        return "Проектов пока нет."
    lines = ["📋 Список проектов:"]
    for r in rows:
        token_part = r['bot_token'][:10] + "..." if r['bot_token'] else "(нет токена)"
        manager_part = " +менеджер" if r['manager_bot_token'] else ""
        lines.append(f"• {r['id']} – {r['name']} (токен: {token_part}{manager_part})")
    return "\n".join(lines)
