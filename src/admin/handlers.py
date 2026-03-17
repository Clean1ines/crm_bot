"""
Admin command handlers for managing projects via Telegram.
FIXED: Delete flow with confirmation buttons, Manager creation flow if empty.
"""

import uuid
import httpx
import asyncpg
import json
import re
from typing import Optional, Dict, Any, Tuple

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from src.database.repositories.project_repository import ProjectRepository
from src.database.repositories.template_repository import TemplateRepository
from src.core.logging import get_logger
from src.core.config import settings
from src.services.redis_client import get_redis_client
from src.admin.keyboards import (
    make_main_menu_keyboard,
    make_project_keyboard,
    make_template_keyboard,
    make_token_help_keyboard,
    make_token_input_hint,
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

# NEW STATES FOR FIXES
STATE_DELETE_AWAIT_CONFIRM = "delete:await_confirm"
STATE_CREATE_MANAGER_AWAIT_TOKEN = "create_manager:await_token"

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
        return await _cmd_start(), None
    elif cmd == "/help":
        return _cmd_help(), None
    # Остальные команды обрабатываются как шаги, если нужно, но пока оставим явными
    return await _process_admin_step(text, None, pool, None, None)

async def _cmd_start() -> AdminResponse:
    text = (
        "👋 **Админ-панель фабрики ботов**\n\n"
        "Я помогу создать и настроить вашего AI-ассистента.\n\n"
        "🔹 **Быстрый старт**:\n"
        "1. Нажмите «🚀 Создать бота»\n"
        "2. Введите название проекта\n"
        "3. Выберите шаблон (или пропустите)\n"
        "4. Вставьте токен из @BotFather\n"
        "5. Готово! 🎉\n\n"
        "📌 Токен и настройки шифруются."
    )
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

    # Existing states
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
    
    # NEW STATES
    elif state == STATE_DELETE_AWAIT_CONFIRM:
        return await _step_delete_confirm(chat_id, text, pool)
    elif state == STATE_CREATE_MANAGER_AWAIT_TOKEN:
        return await _step_create_manager_token(chat_id, text, pool)

    await _clear_state(chat_id)
    return "❌ Диалог сброшен. Напишите /start.", None

# =============================================================================
# STEP IMPLEMENTATIONS
# =============================================================================
async def _step_newproject_start(chat_id: str) -> AdminResponse:
    await _set_state(chat_id, STATE_NEWPROJECT_AWAIT_NAME)
    return "✍️ **Введите название нового проекта**:", None

async def _step_newproject_name(chat_id: str, name: str, pool) -> AdminResponse:
    project_id = await _create_project_raw(name, pool)
    await _set_data(chat_id, {"project_id": project_id})
    await _set_state(chat_id, STATE_NEWPROJECT_AWAIT_TEMPLATE)
    
    text = (
        f"✅ Проект **«{name}»** создан!\nID: `{project_id}`\n\n"
        f"🎯 **Выберите шаблон**:\n"
        f"• 💬 `support`\n• 🎯 `leads`\n• 🛒 `orders`\n• ⚙️ `custom` (Pro)"
    )
    return text, make_template_keyboard()

async def _handle_template_selection(chat_id: str, input_text: str, pool) -> AdminResponse:
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    
    if not project_id:
        await _clear_state(chat_id)
        return "❌ Ошибка: проект не найден. Начните с /start.", None

    if re.match(r'^\d+:[a-zA-Z0-9_-]+$', input_text.strip()):
        return await _step_settoken_token(chat_id, input_text.strip(), pool)

    template_slug = input_text.strip()
    if template_slug.startswith("tpl:"):
        template_slug = template_slug.replace("tpl:", "")
        
        if template_slug.lower() in ("skip", "custom"):
            await _clear_state(chat_id)
            await _set_data(chat_id, {"project_id": project_id})
            await _set_state(chat_id, STATE_SETTOKEN_AWAIT_TOKEN)
            text = (
                f"✅ Шаблон не выбран (режим Custom).\n\n"
                f"🔑 **Отправьте токен бота** следующим сообщением:"
            )
            return text, make_token_help_keyboard()

        template_repo = TemplateRepository(pool)
        template = await template_repo.get_by_slug(template_slug)
        
        if not template:
            return "❌ Шаблон не найден. Выберите кнопку или напишите `skip`.", make_template_keyboard()
        
        project_repo = ProjectRepository(pool)
        success = await project_repo.apply_template(project_id, template_slug)
        
        if not success:
            await _clear_state(chat_id)
            return "❌ Ошибка применения шаблона.", None
        
        await _clear_state(chat_id)
        await _set_data(chat_id, {"project_id": project_id})
        await _set_state(chat_id, STATE_SETTOKEN_AWAIT_TOKEN)
        
        text = (
            f"✅ Шаблон **«{template['name']}»** применён!\n\n"
            f"🔑 **Теперь отправьте токен бота**:"
        )
        return text, make_token_help_keyboard()

    if template_slug.lower() in ("skip", "custom", "пропустить"):
         await _clear_state(chat_id)
         await _set_data(chat_id, {"project_id": project_id})
         await _set_state(chat_id, STATE_SETTOKEN_AWAIT_TOKEN)
         text = (
            f"✅ Пропущено.\n\n"
            f"🔑 **Отправьте токен бота** следующим сообщением:"
        )
         return text, make_token_help_keyboard()

    return "❌ Неверный формат. Выберите кнопку или отправьте токен.", make_template_keyboard()

async def _step_settoken_start(chat_id: str) -> AdminResponse:
    await _set_state(chat_id, STATE_SETTOKEN_AWAIT_PROJECT)
    return "🆔 **Введите ID проекта**:", None

async def _step_settoken_project(chat_id: str, project_id: str, pool) -> AdminResponse:
    try:
        async with pool.acquire() as conn:
            exists = await conn.fetchval("SELECT 1 FROM projects WHERE id = $1", uuid.UUID(project_id))
            if not exists:
                return f"❌ Проект `{project_id}` не найден.", None
    except Exception:
        return "❌ Неверный формат ID.", None
    
    await _set_data(chat_id, {"project_id": project_id})
    await _set_state(chat_id, STATE_SETTOKEN_AWAIT_TOKEN)
    return make_token_input_hint(), None

async def _step_settoken_token(chat_id: str, token: str, pool) -> AdminResponse:
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    
    if not project_id:
        await _clear_state(chat_id)
        return "❌ Контекст проекта утерян. Начните заново через /start.", None

    logger.info("Setting token for project", extra={"project_id": project_id})
    
    result = await cmd_settoken(project_id, token, pool)
    await _clear_state(chat_id)
    
    keyboard = make_project_keyboard(project_id)
    return result, keyboard

# --- MANAGER STEPS ---
async def _step_setmanager_start(chat_id: str) -> AdminResponse:
    await _set_state(chat_id, STATE_SETMANAGER_AWAIT_PROJECT)
    return "🆔 **Введите ID проекта**:", None

async def _step_setmanager_project(chat_id: str, project_id: str, pool) -> AdminResponse:
    try:
        async with pool.acquire() as conn:
            exists = await conn.fetchval("SELECT 1 FROM projects WHERE id = $1", uuid.UUID(project_id))
            if not exists:
                return f"❌ Проект `{project_id}` не найден.", None
    except Exception:
        return "❌ Неверный ID.", None
        
    await _set_data(chat_id, {"project_id": project_id})
    await _set_state(chat_id, STATE_SETMANAGER_AWAIT_TOKEN)
    return "🔑 **Введите токен менеджерского бота**:", None

async def _step_setmanager_token(chat_id: str, manager_token: str, pool) -> AdminResponse:
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    if not project_id:
        await _clear_state(chat_id)
        return "❌ Ошибка: проект не указан.", None
    await _set_data(chat_id, {"project_id": project_id, "manager_token": manager_token})
    await _set_state(chat_id, STATE_SETMANAGER_AWAIT_CHAT_ID)
    return "👤 **Введите chat_id менеджера**:", None

async def _step_setmanager_chat_id(chat_id: str, manager_chat_id: str, pool) -> AdminResponse:
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    manager_token = data.get("manager_token")
    if not project_id or not manager_token:
        await _clear_state(chat_id)
        return "❌ Данные утеряны.", None
    result = await cmd_setmanager(project_id, manager_token, manager_chat_id, pool)
    await _clear_state(chat_id)
    return result, make_project_keyboard(project_id)

# --- NEW: CREATE MANAGER FLOW (if empty) ---
async def _step_create_manager_token(chat_id: str, manager_token: str, pool) -> AdminResponse:
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    if not project_id:
        await _clear_state(chat_id)
        return "❌ Ошибка: проект не указан.", None
    
    # Сразу переходим к запросу chat_id, так как токен уже есть
    await _set_data(chat_id, {"project_id": project_id, "manager_token": manager_token})
    await _set_state(chat_id, STATE_SETMANAGER_AWAIT_CHAT_ID)
    return "👤 **Токен принят! Теперь введите chat_id менеджера**:\n(получите через @echoManagersBot)", None

# --- DELETE STEPS ---
async def _step_delete_confirm(chat_id: str, text: str, pool) -> AdminResponse:
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    project_name = data.get("project_name")
    
    if not project_id:
        await _clear_state(chat_id)
        return "❌ Ошибка: проект не найден.", None
    
    if text.strip().lower() == "да":
        # Удаляем проект
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

async def _step_listmanagers_project(chat_id: str, project_id: str, pool) -> str:
    result = await cmd_listmanagers(project_id, pool)
    await _clear_state(chat_id)
    return result

async def _step_promode_start(chat_id: str) -> AdminResponse:
    await _set_state(chat_id, STATE_PROMODE_AWAIT_PROJECT)
    return "🆔 **ID проекта**:", None

async def _step_promode_project(chat_id: str, project_id: str, pool) -> AdminResponse:
    try:
        async with pool.acquire() as conn:
            exists = await conn.fetchval("SELECT 1 FROM projects WHERE id = $1", uuid.UUID(project_id))
            if not exists:
                return f"❌ Проект не найден.", None
    except Exception:
        return "❌ Неверный ID.", None
        
    await _set_data(chat_id, {"project_id": project_id})
    await _set_state(chat_id, STATE_PROMODE_AWAIT_ENABLED)
    return "⚙️ Введите `on` или `off`:", None

async def _step_promode_enabled(chat_id: str, value: str, pool) -> AdminResponse:
    data = await _get_data(chat_id)
    project_id = data.get("project_id")
    if not project_id:
        await _clear_state(chat_id)
        return "❌ Ошибка.", None
    enabled = value.lower() in ("on", "true", "1", "yes")
    result = await cmd_set_pro_mode(project_id, enabled, pool)
    await _clear_state(chat_id)
    return result, make_project_keyboard(project_id)

# =============================================================================
# CALLBACK HANDLER
# =============================================================================
async def handle_admin_callback(callback_data: str, chat_id: str, pool) -> AdminResponse:
    logger.info("Callback", extra={"data": callback_data, "chat_id": chat_id})

    if callback_data == "newproject":
        return await _step_newproject_start(chat_id)
    
    elif callback_data == "listprojects":
        return await cmd_listprojects(pool), None
    
    elif callback_data == "help":
        return _cmd_help(), None
    
    elif callback_data == "settings":
        return "⚙️ Настройки в разработке.", None
    
    elif callback_data == "help_token":
        return make_token_input_hint(), None
    
    elif callback_data.startswith("settoken:"):
        pid = callback_data.split(":")[1]
        await _set_data(chat_id, {"project_id": pid})
        await _set_state(chat_id, STATE_SETTOKEN_AWAIT_TOKEN)
        return make_token_input_hint(), None
    
    elif callback_data.startswith("managers:"):
        pid = callback_data.split(":")[1]
        # FIX: Check if managers exist
        managers = await ProjectRepository(pool).get_managers(pid)
        if not managers:
            # No managers -> Offer to create
            await _set_data(chat_id, {"project_id": pid})
            await _set_state(chat_id, STATE_CREATE_MANAGER_AWAIT_TOKEN)
            text = (
                f"📭 Для проекта `{pid}` нет менеджеров.\n\n"
                f"🔑 **Давайте настроим менеджерского бота**:\n"
                f"1. Создайте бота в @BotFather (/newbot).\n"
                f"2. Скопируйте токен.\n"
                f"3. Отправьте его мне следующим сообщением."
            )
            return text, make_token_help_keyboard()
        else:
            # Managers exist -> List them
            lines = [f"👥 **Менеджеры проекта** `{pid}`:"]
            for i, cid in enumerate(managers, 1):
                lines.append(f"{i}. `{cid}`")
            text = "\n".join(lines)
            return text, make_project_keyboard(pid)
    
    elif callback_data.startswith("knowledge:"):
        pid = callback_data.split(":")[1]
        return f"📚 Загрузка знаний для `{pid}`. Отправьте файл.", None
    
    elif callback_data.startswith("promode:"):
        pid = callback_data.split(":")[1]
        await _set_data(chat_id, {"project_id": pid})
        await _set_state(chat_id, STATE_PROMODE_AWAIT_ENABLED)
        return "⚙️ Введите `on` или `off`:", None
    
    elif callback_data.startswith("delete:"):
        pid = callback_data.split(":")[1]
        # FIX: Get project name and ask for confirmation
        try:
            async with pool.acquire() as conn:
                row = await conn.fetchrow("SELECT name FROM projects WHERE id = $1", uuid.UUID(pid))
                if not row:
                    return "❌ Проект не найден.", None
                pname = row["name"]
        except Exception:
            return "❌ Ошибка получения данных проекта.", None
            
        await _set_data(chat_id, {"project_id": pid, "project_name": pname})
        await _set_state(chat_id, STATE_DELETE_AWAIT_CONFIRM)
        
        text = (
            f"🗑️ **Вы уверены, что хотите удалить проект?**\n\n"
            f"Название: **{pname}**\n"
            f"ID: `{pid}`\n\n"
            f"⚠️ Это действие НЕОБРАТИМО! Все данные будут удалены.\n\n"
            f"Для подтверждения введите слово **да** (без кавычек)."
        )
        return text, None
    
    elif callback_data.startswith("tpl:"):
        return await _handle_template_selection(chat_id, callback_data, pool)
    
    return "❌ Неизвестная кнопка.", None

# =============================================================================
# CORE LOGIC
# =============================================================================
async def _create_project_raw(name: str, pool) -> str:
    logger.info("Creating project", extra={"name": name})
    temp_owner_id = str(uuid.uuid4())
    
    async with pool.acquire() as conn:
        project_id = await conn.fetchval("""
            INSERT INTO projects (id, name, owner_id, bot_token, system_prompt)
            VALUES (gen_random_uuid(), $1, $2, '', 'Ты — полезный AI-ассистент.')
            RETURNING id
        """, name, temp_owner_id)
    
    logger.info("Project created", extra={"project_id": project_id})
    return str(project_id)

async def cmd_newproject(name: str, pool) -> str:
    pid = await _create_project_raw(name, pool)
    return f"✅ Проект «{name}» создан.\nID: `{pid}`\n\n🔑 Далее: `/settoken {pid} <токен>`"

async def cmd_settoken(project_id: str, token: str, pool) -> str:
    secret_token = uuid.uuid4().hex
    project_repo = ProjectRepository(pool)
    try:
        await project_repo.set_bot_token(project_id, token)
        await project_repo.set_webhook_secret(project_id, secret_token)
    except Exception as e:
        logger.exception("Token error", extra={"error": str(e)})
        return f"❌ Ошибка: {str(e)}"
    
    base_url = settings.RENDER_EXTERNAL_URL or settings.PUBLIC_URL
    if not base_url:
        return "❌ PUBLIC_URL не задан."
    
    webhook_url = f"{base_url.rstrip('/')}/webhook/{project_id}"
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(
                f"https://api.telegram.org/bot{token}/setWebhook",
                json={"url": webhook_url, "secret_token": secret_token}
            )
            if resp.status_code != 200:
                err = resp.json().get("description", f"HTTP {resp.status_code}")
                return f"❌ Вебхук не установлен: {err}"
            if not resp.json().get("ok"):
                return f"❌ Telegram: {resp.json().get('description')}"
        except Exception as e:
            return f"❌ Ошибка сети: {str(e)}"
    
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            username = r.json()["result"]["username"] if r.json().get("ok") else None
    except:
        username = None
    
    link = f"https://t.me/{username}" if username else f"https://t.me/{project_id}"
    return (
        f"✅ Токен установлен!\nВебхук: `{webhook_url}`\n\n"
        f"🤖 **Ваш бот**: {link}\n🔐 Секрет сохранён."
    )

async def cmd_setmanager(project_id: str, manager_token: str, manager_chat_id: Optional[str], pool) -> str:
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
                return f"❌ Telegram: {resp.json().get('description')}"
        except Exception as e:
            return f"❌ Ошибка: {str(e)}"
    
    msg = f"✅ Менеджерский бот настроен!"
    if manager_chat_id:
        msg += f"\n👤 Менеджер `{manager_chat_id}` добавлен."
    return msg

async def cmd_listmanagers(project_id: str, pool) -> str:
    managers = await ProjectRepository(pool).get_managers(project_id)
    if not managers:
        return f"📭 Для проекта `{project_id}` нет менеджеров."
    lines = [f"👥 **Менеджеры проекта** `{project_id}`:"]
    for i, cid in enumerate(managers, 1):
        lines.append(f"{i}. `{cid}`")
    return "\n".join(lines)

async def cmd_removemanager(project_id: str, manager_chat_id: str, pool) -> str:
    try:
        await ProjectRepository(pool).remove_manager(project_id, manager_chat_id)
        return f"✅ Менеджер `{manager_chat_id}` удалён."
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"

async def cmd_listprojects(pool) -> str:
    async with pool.acquire() as conn:
        rows = await conn.fetch("""
            SELECT id, name, bot_token, manager_bot_token, template_slug, is_pro_mode, created_at
            FROM projects ORDER BY created_at DESC
        """)
    if not rows:
        return "📭 Проектов нет."
    lines = ["📦 **Ваши проекты**:"]
    for r in rows:
        st = []
        if r['bot_token']: st.append("🔑")
        if r['manager_bot_token']: st.append("👥")
        if r['template_slug']: st.append(f"📦{r['template_slug']}")
        if r['is_pro_mode']: st.append("⭐Pro")
        dt = r['created_at'].strftime("%d.%m") if r['created_at'] else "?"
        lines.append(f"• `{r['id']}` — {r['name']} {' '.join(st)} | {dt}")
    
    # Add a hint about deletion
    lines.append("\n💡 Нажмите на проект в списке (если бы это были кнопки) или используйте команду /delete.")
    return "\n".join(lines)

async def cmd_set_pro_mode(project_id: str, enabled: bool, pool) -> str:
    try:
        await ProjectRepository(pool).set_pro_mode(project_id, enabled)
        status = "✅ включён" if enabled else "❌ отключён"
        extra = "🎨 Канвас доступен!" if enabled else "⚙️ Шаблоны."
        return f"✅ Pro-режим для `{project_id}` {status}.\n{extra}"
    except Exception as e:
        return f"❌ Ошибка: {str(e)}"
