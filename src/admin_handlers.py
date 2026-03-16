"""
Admin command handlers for managing projects via Telegram.
"""

import uuid
import os
import httpx
import asyncpg
from src.database.repositories.project_repository import ProjectRepository
from src.core.logging import get_logger

logger = get_logger(__name__)

async def handle_admin_command(text: str, pool) -> str:
    """Разбирает админ-команду и возвращает текст ответа."""
    parts = text.strip().split()
    if not parts:
        return "Пустая команда."

    cmd = parts[0].lower()
    logger.info(f"Admin command received: {cmd}", extra={"args": parts[1:]})

    if cmd == "/start":
        return ("👋 Администратор фабрики ботов опознан!\n\n"
                "Доступные команды:\n"
                "• /newproject <название> – создать новый проект\n"
                "• /settoken <project_id> <токен> – привязать токен к проекту и установить вебхук\n"
                "• /listprojects – список всех проектов\n"
                "• /help – показать эту справку")

    elif cmd == "/help":
        return ("Доступные команды:\n"
                "/start – приветствие\n"
                "/newproject <название> – создать новый проект\n"
                "/settoken <project_id> <токен> – привязать токен\n"
                "/listprojects – список проектов")

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

    elif cmd == "/listprojects":
        return await cmd_listprojects(pool)

    else:
        logger.warning(f"Unknown admin command: {cmd}")
        return f"Неизвестная команда: {cmd}"

async def cmd_newproject(name: str, pool) -> str:
    """Создаёт новый проект, возвращает его ID."""
    logger.info(f"Creating new project with name: {name}")
    async with pool.acquire() as conn:
        project_repo = ProjectRepository(pool)  # передаём pool, внутри он сам возьмёт соединение
        # Временный токен – пустой, позже установит админ через /settoken
        project_id = await conn.fetchval("""
            INSERT INTO projects (id, name, owner_id, bot_token, system_prompt)
            VALUES (gen_random_uuid(), $1, 'admin', '', 'Ты — полезный AI-ассистент.')
            RETURNING id
        """, name)
    logger.info(f"Project created successfully: {project_id}")
    return f"✅ Проект «{name}» создан.\nID: {project_id}\nТеперь установи токен командой /settoken {project_id} <токен>"

async def cmd_settoken(project_id: str, token: str, pool) -> str:
    """Устанавливает токен бота для проекта и автоматически настраивает вебхук."""
    logger.info(f"Setting token for project {project_id}")
    async with pool.acquire() as conn:
        # Обновляем токен в БД
        result = await conn.execute("""
            UPDATE projects SET bot_token = $1 WHERE id = $2
        """, token, uuid.UUID(project_id))
        if result.split()[-1] == "0":
            logger.warning(f"Project {project_id} not found")
            return f"❌ Проект с ID {project_id} не найден."

    # Получаем базовый URL сервиса из переменной окружения
    base_url = settings.RENDER_EXTERNAL_URL or settings.PUBLIC_URL
    if not base_url:
        logger.error("RENDER_EXTERNAL_URL or PUBLIC_URL not set")
        return "❌ Не удалось определить публичный URL сервиса. Убедитесь, что переменная RENDER_EXTERNAL_URL или PUBLIC_URL задана."

    webhook_url = f"{base_url.rstrip('/')}/webhook/{project_id}"

    # Вызываем Telegram API для установки вебхука
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
            # Проверяем поле ok в ответе
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

async def cmd_listprojects(pool) -> str:
    """Возвращает список проектов с их ID и названиями."""
    logger.info("Listing all projects")
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT id, name, bot_token FROM projects ORDER BY created_at DESC")
    if not rows:
        return "Проектов пока нет."
    lines = ["📋 Список проектов:"]
    for r in rows:
        token_part = r['bot_token'][:10] + "..." if r['bot_token'] else "(нет токена)"
        lines.append(f"• {r['id']} – {r['name']} (токен: {token_part})")
    return "\n".join(lines)
