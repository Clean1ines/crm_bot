"""
Project Repository for multi-tenant bot platform.

This module provides data access methods for project configuration,
including bot tokens, manager settings, and workflow template tracking.
"""

import uuid
import asyncpg
import httpx
from typing import Optional, Dict, Any, List, Union

from src.core.logging import get_logger
from src.utils.encryption import encrypt_token, decrypt_token
from src.core.config import settings

logger = get_logger(__name__)


def _ensure_uuid(project_id: Union[str, uuid.UUID]) -> uuid.UUID:
    """
    Convert project_id to UUID object if it's a string, return as is if already UUID.
    """
    if isinstance(project_id, uuid.UUID):
        return project_id
    return uuid.UUID(project_id)


class ProjectRepository:
    """
    Repository for managing project-level data and configuration.
    
    Handles encrypted storage of bot tokens, manager assignments,
    and workflow template tracking for multi-tenant isolation.
    
    Attributes:
        pool: Asyncpg connection pool for database operations.
    """
    
    def __init__(self, pool: asyncpg.Pool) -> None:
        """
        Initialize the ProjectRepository with a database connection pool.
        
        Args:
            pool: Asyncpg connection pool for database operations.
        """
        self.pool = pool
        logger.debug("ProjectRepository initialized")
    
    # ------------------------------------------------------------------
    # Private helpers to encrypt/decrypt token fields
    # ------------------------------------------------------------------
    def _encrypt_if_present(self, token: Optional[str]) -> Optional[str]:
        """
        Encrypt a token if it is present, otherwise return None.
        
        Args:
            token: The token string to encrypt.
        
        Returns:
            Encrypted token or None.
        """
        return encrypt_token(token) if token else None

    def _decrypt_if_present(self, encrypted: Optional[str]) -> Optional[str]:
        """
        Decrypt a token if it is present, otherwise return None.
        
        Args:
            encrypted: The encrypted token string.
        
        Returns:
            Decrypted token or None.
        """
        return decrypt_token(encrypted) if encrypted else None

    async def _get_bot_username(self, token: str) -> Optional[str]:
        """
        Get bot username from Telegram API using the token.
        
        Args:
            token: Bot token (unencrypted).
        
        Returns:
            Username of the bot (without @) or None if request fails.
        """
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"https://api.telegram.org/bot{token}/getMe",
                    timeout=5.0
                )
                if resp.status_code == 200 and resp.json().get("ok"):
                    return resp.json()["result"]["username"]
        except Exception as e:
            logger.warning("Failed to fetch bot username", extra={"error": str(e)})
        return None

    # ------------------------------------------------------------------
    # Public methods - Core project settings
    # ------------------------------------------------------------------
    async def get_project_settings(self, project_id: Union[str, uuid.UUID]) -> Dict[str, Any]:
        """
        Возвращает настройки проекта: system_prompt, bot_token, webhook_url,
        manager_bot_token, webhook_secret и список manager_chat_ids.
        Если проект не найден, возвращает пустой словарь.
        
        Args:
            project_id: UUID проекта в строковом формате или объект UUID.
        
        Returns:
            Dict с настройками проекта или пустой dict если проект не найден.
        """
        logger.info("Fetching project settings", extra={"project_id": str(project_id)})
        async with self.pool.acquire() as conn:
            # Получаем основные поля проекта
            row = await conn.fetchrow("""
                SELECT system_prompt, bot_token, webhook_url, manager_bot_token, 
                       webhook_secret, template_slug, is_pro_mode,
                       client_bot_username, manager_bot_username
                FROM projects
                WHERE id = $1
            """, _ensure_uuid(project_id))
            if not row:
                logger.warning("Project not found", extra={"project_id": str(project_id)})
                return {}

            settings = dict(row)
            # Decrypt tokens
            settings["bot_token"] = self._decrypt_if_present(settings["bot_token"])
            settings["manager_bot_token"] = self._decrypt_if_present(settings["manager_bot_token"])

            # Получаем список manager_chat_ids из таблицы project_managers
            manager_rows = await conn.fetch("""
                SELECT manager_chat_id FROM project_managers
                WHERE project_id = $1
            """, _ensure_uuid(project_id))
            settings["manager_chat_ids"] = [r["manager_chat_id"] for r in manager_rows]

            logger.info("Project settings retrieved", extra={"project_id": str(project_id)})
            return settings

    async def get_bot_token(self, project_id: Union[str, uuid.UUID]) -> Optional[str]:
        """
        Возвращает только bot_token для проекта (расшифрованный).
        
        Args:
            project_id: UUID проекта в строковом формате или объект UUID.
        
        Returns:
            Расшифрованный токен бота или None.
        """
        logger.info("Fetching bot token", extra={"project_id": str(project_id)})
        async with self.pool.acquire() as conn:
            encrypted = await conn.fetchval("""
                SELECT bot_token FROM projects WHERE id = $1
            """, _ensure_uuid(project_id))
            token = self._decrypt_if_present(encrypted)
            if token:
                logger.info("Bot token found", extra={"project_id": str(project_id)})
            else:
                logger.warning("No bot token found", extra={"project_id": str(project_id)})
            return token

    async def set_bot_token(self, project_id: Union[str, uuid.UUID], token: Optional[str]) -> None:
        """
        Устанавливает bot_token для проекта (шифрует перед сохранением).
        Также обновляет client_bot_username, получая его из Telegram API.
        
        Args:
            project_id: UUID проекта в строковом формате или объект UUID.
            token: Токен бота для шифрования и сохранения (None для удаления).
        """
        logger.info("Setting bot token", extra={"project_id": str(project_id)})
        encrypted = self._encrypt_if_present(token)
        username = None
        if token:
            username = await self._get_bot_username(token)
            if username:
                logger.info("Bot username resolved", extra={"username": username})
            else:
                logger.warning("Could not fetch bot username from token")
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE projects 
                SET bot_token = $1, client_bot_username = $2, updated_at = NOW()
                WHERE id = $3
            """, encrypted, username, _ensure_uuid(project_id))

    async def get_manager_bot_token(self, project_id: Union[str, uuid.UUID]) -> Optional[str]:
        """
        Возвращает manager_bot_token для проекта (расшифрованный).
        
        Args:
            project_id: UUID проекта в строковом формате или объект UUID.
        
        Returns:
            Расшифрованный токен менеджерского бота или None.
        """
        logger.info("Fetching manager bot token", extra={"project_id": str(project_id)})
        async with self.pool.acquire() as conn:
            encrypted = await conn.fetchval("""
                SELECT manager_bot_token FROM projects WHERE id = $1
            """, _ensure_uuid(project_id))
            token = self._decrypt_if_present(encrypted)
            if token:
                logger.info("Manager bot token found", extra={"project_id": str(project_id)})
            else:
                logger.warning("No manager bot token found", extra={"project_id": str(project_id)})
            return token

    async def set_manager_bot_token(self, project_id: Union[str, uuid.UUID], token: Optional[str]) -> None:
        """
        Устанавливает manager_bot_token для проекта (шифрует перед сохранением).
        Также обновляет manager_bot_username, получая его из Telegram API.
        
        Args:
            project_id: UUID проекта в строковом формате или объект UUID.
            token: Токен менеджерского бота для шифрования и сохранения (None для удаления).
        """
        logger.info("Setting manager bot token", extra={"project_id": str(project_id)})
        encrypted = self._encrypt_if_present(token)
        username = None
        if token:
            username = await self._get_bot_username(token)
            if username:
                logger.info("Manager bot username resolved", extra={"username": username})
            else:
                logger.warning("Could not fetch manager bot username from token")
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE projects 
                SET manager_bot_token = $1, manager_bot_username = $2, updated_at = NOW()
                WHERE id = $3
            """, encrypted, username, _ensure_uuid(project_id))

    async def get_webhook_secret(self, project_id: Union[str, uuid.UUID]) -> Optional[str]:
        """
        Возвращает webhook_secret для проекта.
        
        Args:
            project_id: UUID проекта в строковом формате или объект UUID.
        
        Returns:
            Webhook secret или None.
        """
        logger.debug("Fetching webhook secret", extra={"project_id": str(project_id)})
        async with self.pool.acquire() as conn:
            secret = await conn.fetchval("""
                SELECT webhook_secret FROM projects WHERE id = $1
            """, _ensure_uuid(project_id))
            return secret

    async def set_webhook_secret(self, project_id: Union[str, uuid.UUID], secret: str) -> None:
        """
        Устанавливает webhook_secret для проекта.
        
        Args:
            project_id: UUID проекта в строковом формате или объект UUID.
            secret: Webhook secret для сохранения.
        """
        logger.info("Setting webhook secret", extra={"project_id": str(project_id)})
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE projects SET webhook_secret = $1, updated_at = NOW()
                WHERE id = $2
            """, secret, _ensure_uuid(project_id))

    # ------------------------------------------------------------------
    # Manager management
    # ------------------------------------------------------------------
    async def get_managers(self, project_id: Union[str, uuid.UUID]) -> List[str]:
        """
        Возвращает список manager_chat_id для проекта.
        
        Args:
            project_id: UUID проекта в строковом формате или объект UUID.
        
        Returns:
            Список chat_id менеджеров.
        """
        logger.debug("Fetching managers", extra={"project_id": str(project_id)})
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT manager_chat_id FROM project_managers
                WHERE project_id = $1
            """, _ensure_uuid(project_id))
            return [r["manager_chat_id"] for r in rows]

    async def add_manager(self, project_id: Union[str, uuid.UUID], manager_chat_id: str) -> None:
        """
        Добавляет менеджера (chat_id) в список менеджеров проекта.
        Игнорирует дубликаты.
        
        Args:
            project_id: UUID проекта в строковом формате или объект UUID.
            manager_chat_id: Telegram chat_id менеджера.
        """
        logger.info("Adding manager", extra={"project_id": str(project_id), "manager_chat_id": manager_chat_id})
        async with self.pool.acquire() as conn:
            try:
                await conn.execute("""
                    INSERT INTO project_managers (project_id, manager_chat_id)
                    VALUES ($1, $2)
                """, _ensure_uuid(project_id), manager_chat_id)
            except asyncpg.exceptions.UniqueViolationError:
                logger.warning(
                    "Manager already exists",
                    extra={"project_id": str(project_id), "manager_chat_id": manager_chat_id}
                )

    async def remove_manager(self, project_id: Union[str, uuid.UUID], manager_chat_id: str) -> None:
        """
        Удаляет менеджера (chat_id) из списка менеджеров проекта.
        
        Args:
            project_id: UUID проекта в строковом формате или объект UUID.
            manager_chat_id: Telegram chat_id менеджера для удаления.
        """
        logger.info("Removing manager", extra={"project_id": str(project_id), "manager_chat_id": manager_chat_id})
        async with self.pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM project_managers
                WHERE project_id = $1 AND manager_chat_id = $2
            """, _ensure_uuid(project_id), manager_chat_id)

    # ------------------------------------------------------------------
    # Template & Pro mode management
    # ------------------------------------------------------------------
    async def apply_template(self, project_id: Union[str, uuid.UUID], template_slug: str) -> bool:
        """
        Применяет шаблон воркфлоу к проекту.
        
        Устанавливает template_slug для проекта, что указывает оркестратору
        использовать предопределённый граф из workflow_templates.
        
        Args:
            project_id: UUID проекта в строковом формате или объект UUID.
            template_slug: Уникальный slug шаблона (например, 'support', 'leads').
        
        Returns:
            True если шаблон применён успешно, False если шаблон не найден.
        """
        logger.info(
            "Applying template to project",
            extra={"project_id": str(project_id), "template_slug": template_slug}
        )
        
        # Проверяем существование шаблона
        async with self.pool.acquire() as conn:
            template_exists = await conn.fetchval(
                "SELECT 1 FROM workflow_templates WHERE slug = $1 AND is_active = true",
                template_slug
            )
            if not template_exists:
                logger.warning(
                    "Template not found",
                    extra={"project_id": str(project_id), "template_slug": template_slug}
                )
                return False
            
            # Применяем шаблон
            await conn.execute("""
                UPDATE projects 
                SET template_slug = $1, updated_at = NOW()
                WHERE id = $2
            """, template_slug, _ensure_uuid(project_id))
            
            logger.info(
                "Template applied successfully",
                extra={"project_id": str(project_id), "template_slug": template_slug}
            )
            return True

    async def set_pro_mode(self, project_id: Union[str, uuid.UUID], enabled: bool) -> None:
        """
        Включает или отключает Pro mode для проекта.
        
        Pro mode даёт доступ к custom workflow canvas и расширенным функциям.
        
        Args:
            project_id: UUID проекта в строковом формате или объект UUID.
            enabled: True для включения Pro mode, False для отключения.
        """
        logger.info(
            "Setting pro mode",
            extra={"project_id": str(project_id), "enabled": enabled}
        )
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE projects 
                SET is_pro_mode = $1, updated_at = NOW()
                WHERE id = $2
            """, enabled, _ensure_uuid(project_id))

    async def get_template_slug(self, project_id: Union[str, uuid.UUID]) -> Optional[str]:
        """
        Возвращает slug применённого шаблона для проекта.
        
        Args:
            project_id: UUID проекта в строковом формате или объект UUID.
        
        Returns:
            Slug шаблона или None если шаблон не применён.
        """
        logger.debug("Getting template slug", extra={"project_id": str(project_id)})
        async with self.pool.acquire() as conn:
            slug = await conn.fetchval(
                "SELECT template_slug FROM projects WHERE id = $1",
                _ensure_uuid(project_id)
            )
            return slug

    async def get_is_pro_mode(self, project_id: Union[str, uuid.UUID]) -> bool:
        """
        Проверяет, включён ли Pro mode для проекта.
        
        Args:
            project_id: UUID проекта в строковом формате или объект UUID.
        
        Returns:
            True если Pro mode включён, False иначе.
        """
        logger.debug("Checking pro mode", extra={"project_id": str(project_id)})
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT is_pro_mode FROM projects WHERE id = $1",
                _ensure_uuid(project_id)
            )
            return bool(result)

    # ------------------------------------------------------------------
    # Find project by manager token (for webhook routing)
    # ------------------------------------------------------------------
    async def find_project_by_manager_token(self, raw_token: str) -> Optional[str]:
        """
        Находит проект по raw токену менеджерского бота.
        Перебирает все проекты, расшифровывает manager_bot_token и сравнивает с raw_token.
        
        Args:
            raw_token: Токен менеджерского бота (нешифрованный).
        
        Returns:
            project_id в виде строки или None, если не найдено.
        """
        logger.info("Searching project by manager token")
        async with self.pool.acquire() as conn:
            # Получаем все id и зашифрованные manager_bot_token
            rows = await conn.fetch("SELECT id, manager_bot_token FROM projects WHERE manager_bot_token IS NOT NULL")
            for row in rows:
                encrypted = row["manager_bot_token"]
                if not encrypted:
                    continue
                decrypted = decrypt_token(encrypted)
                if decrypted == raw_token:
                    logger.info("Project found by manager token", extra={"project_id": str(row["id"])})
                    return str(row["id"])
        logger.info("No project found with given manager token")
        return None

    # ------------------------------------------------------------------
    # Manager webhook secret
    # ------------------------------------------------------------------
    async def get_manager_webhook_secret(self, project_id: Union[str, uuid.UUID]) -> Optional[str]:
        """
        Возвращает manager_webhook_secret для проекта.
        
        Args:
            project_id: UUID проекта в строковом формате или объект UUID.
        
        Returns:
            Секретный токен или None.
        """
        logger.debug("Fetching manager webhook secret", extra={"project_id": str(project_id)})
        async with self.pool.acquire() as conn:
            secret = await conn.fetchval("""
                SELECT manager_webhook_secret FROM projects WHERE id = $1
            """, _ensure_uuid(project_id))
            return secret

    async def set_manager_webhook_secret(self, project_id: Union[str, uuid.UUID], secret: str) -> None:
        """
        Устанавливает manager_webhook_secret для проекта.
        
        Args:
            project_id: UUID проекта в строковом формате или объект UUID.
            secret: Секретный токен для сохранения.
        """
        logger.info("Setting manager webhook secret", extra={"project_id": str(project_id)})
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE projects SET manager_webhook_secret = $1, updated_at = NOW()
                WHERE id = $2
            """, secret, _ensure_uuid(project_id))

    async def find_project_by_manager_webhook_secret(self, secret: str) -> Optional[str]:
        """
        Находит проект по manager_webhook_secret.
        
        Args:
            secret: Секретный токен.
        
        Returns:
            project_id в виде строки или None, если не найдено.
        """
        logger.info("Searching project by manager webhook secret")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id FROM projects WHERE manager_webhook_secret = $1
            """, secret)
            if row:
                project_id = str(row["id"])
                logger.info("Project found by manager webhook secret", extra={"project_id": project_id})
                return project_id
            logger.info("No project found with given manager webhook secret")
            return None

    # ------------------------------------------------------------------
    # Project CRUD operations (with user_id support)
    # ------------------------------------------------------------------
    async def project_exists(self, project_id: Union[str, uuid.UUID]) -> bool:
        """
        Проверяет, существует ли проект с указанным ID.
        
        Args:
            project_id: UUID проекта в строковом формате или объект UUID.
        
        Returns:
            True если проект существует, False иначе.
        """
        logger.debug("Checking project existence", extra={"project_id": str(project_id)})
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT 1 FROM projects WHERE id = $1", 
                _ensure_uuid(project_id)
            )
            return result is not None

    async def create_project(self, owner_id: str, name: str) -> str:
        """
        Создаёт новый проект с owner_id (строка, может быть telegram_id или user_id).
        Для обратной совместимости с админ-ботом.
        
        Args:
            owner_id: Идентификатор владельца (telegram_id или user_id).
            name: Название проекта.
        
        Returns:
            UUID проекта в виде строки.
        """
        logger.info("Creating project", extra={"owner_id": owner_id, "name": name})
        async with self.pool.acquire() as conn:
            project_id = await conn.fetchval("""
                INSERT INTO projects (id, name, owner_id, bot_token, system_prompt)
                VALUES (gen_random_uuid(), $1, $2, '', 'Ты — полезный AI-ассистент.')
                RETURNING id
            """, name, owner_id)
        logger.info("Project created", extra={"project_id": project_id})
        return str(project_id)

    async def create_project_with_user_id(self, user_id: str, name: str) -> str:
        """
        Создаёт новый проект для пользователя (по user_id).
        Заполняет оба поля owner_id и user_id.
        
        Args:
            user_id: UUID пользователя.
            name: Название проекта.
        
        Returns:
            UUID проекта в виде строки.
        """
        logger.info("Creating project with user_id", extra={"user_id": user_id, "name": name})
        async with self.pool.acquire() as conn:
            project_id = await conn.fetchval("""
                INSERT INTO projects (id, name, owner_id, user_id, bot_token, system_prompt)
                VALUES (gen_random_uuid(), $1, $2, $2, '', 'Ты — полезный AI-ассистент.')
                RETURNING id
            """, name, user_id)
        logger.info("Project created", extra={"project_id": project_id})
        return str(project_id)

    async def get_all_projects(self) -> List[Dict[str, Any]]:
        """
        Возвращает список всех проектов.
        
        Returns:
            Список словарей с полями id, owner_id, user_id, name, is_pro_mode, template_slug, created_at, updated_at.
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, owner_id, user_id, name, is_pro_mode, template_slug, created_at, updated_at
                FROM projects
                ORDER BY created_at DESC
            """)
            projects = []
            for row in rows:
                proj = dict(row)
                proj["id"] = str(proj["id"])
                if proj.get("owner_id"):
                    proj["owner_id"] = str(proj["owner_id"])
                if proj.get("user_id"):
                    proj["user_id"] = str(proj["user_id"])
                projects.append(proj)
            return projects

    async def get_project_by_id(self, project_id: Union[str, uuid.UUID]) -> Optional[Dict[str, Any]]:
        """
        Возвращает один проект по ID, включая поля owner_id, user_id.
        
        Args:
            project_id: UUID проекта в строковом формате или объект UUID.
        
        Returns:
            Словарь с данными проекта или None.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, owner_id, user_id, name, is_pro_mode, template_slug, created_at, updated_at,
                       client_bot_username, manager_bot_username
                FROM projects
                WHERE id = $1
            """, _ensure_uuid(project_id))
            if not row:
                return None
            proj = dict(row)
            proj["id"] = str(proj["id"])
            if proj.get("owner_id"):
                proj["owner_id"] = str(proj["owner_id"])
            if proj.get("user_id"):
                proj["user_id"] = str(proj["user_id"])
            return proj

    async def update_project(self, project_id: Union[str, uuid.UUID], name: Optional[str]) -> None:
        """
        Обновляет имя проекта.
        
        Args:
            project_id: UUID проекта.
            name: Новое имя (если None, не изменяется).
        """
        if name is None:
            return
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE projects SET name = $1, updated_at = NOW()
                WHERE id = $2
            """, name, _ensure_uuid(project_id))

    async def delete_project(self, project_id: Union[str, uuid.UUID]) -> None:
        """
        Удаляет проект (каскадно удалит связанные данные).
        
        Args:
            project_id: UUID проекта.
        """
        async with self.pool.acquire() as conn:
            await conn.execute("DELETE FROM projects WHERE id = $1", _ensure_uuid(project_id))

    async def get_projects_by_owner(self, owner_id: str) -> List[Dict[str, Any]]:
        """
        Возвращает список проектов владельца (owner_id может быть telegram_id или user_id).
        Используется в админ-боте.
        
        Args:
            owner_id: Идентификатор владельца (строка).
        
        Returns:
            Список проектов.
        """
        logger.info("Fetching projects by owner", extra={"owner_id": owner_id})
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, name, is_pro_mode, template_slug, created_at, updated_at,
                       client_bot_username, manager_bot_username
                FROM projects
                WHERE owner_id = $1
                ORDER BY created_at DESC
            """, owner_id)
            projects = []
            for row in rows:
                proj = dict(row)
                proj["id"] = str(proj["id"])
                projects.append(proj)
            return projects

    async def get_projects_by_user_id(self, user_id: str) -> List[Dict[str, Any]]:
        """
        Возвращает список проектов, привязанных к пользователю по user_id.
        Включает поля client_bot_username и manager_bot_username.
        
        Args:
            user_id: UUID пользователя.
        
        Returns:
            Список проектов с полями id, name, is_pro_mode, template_slug, created_at, updated_at, user_id,
            client_bot_username, manager_bot_username.
        """
        logger.info("Fetching projects by user_id", extra={"user_id": user_id})
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, name, is_pro_mode, template_slug, created_at, updated_at,
                       client_bot_username, manager_bot_username
                FROM projects
                WHERE user_id = $1
                ORDER BY created_at DESC
            """, user_id)
            projects = []
            for row in rows:
                proj = dict(row)
                proj["id"] = str(proj["id"])
                proj["user_id"] = user_id
                projects.append(proj)
            return projects
