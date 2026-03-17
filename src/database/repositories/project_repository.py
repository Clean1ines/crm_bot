"""
Project Repository for multi-tenant bot platform.

This module provides data access methods for project configuration,
including bot tokens, manager settings, and workflow template tracking.
"""

import uuid
import asyncpg
from typing import Optional, Dict, Any, List

from src.core.logging import get_logger
from src.utils.encryption import encrypt_token, decrypt_token

logger = get_logger(__name__)


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

    # ------------------------------------------------------------------
    # Public methods - Core project settings
    # ------------------------------------------------------------------
    async def get_project_settings(self, project_id: str) -> Dict[str, Any]:
        """
        Возвращает настройки проекта: system_prompt, bot_token, webhook_url,
        manager_bot_token, webhook_secret и список manager_chat_ids.
        Если проект не найден, возвращает пустой словарь.
        
        Args:
            project_id: UUID проекта в строковом формате.
        
        Returns:
            Dict с настройками проекта или пустой dict если проект не найден.
        """
        logger.info("Fetching project settings", extra={"project_id": project_id})
        async with self.pool.acquire() as conn:
            # Получаем основные поля проекта
            row = await conn.fetchrow("""
                SELECT system_prompt, bot_token, webhook_url, manager_bot_token, 
                       webhook_secret, template_slug, is_pro_mode
                FROM projects
                WHERE id = $1
            """, uuid.UUID(project_id))
            if not row:
                logger.warning("Project not found", extra={"project_id": project_id})
                return {}

            settings = dict(row)
            # Decrypt tokens
            settings["bot_token"] = self._decrypt_if_present(settings["bot_token"])
            settings["manager_bot_token"] = self._decrypt_if_present(settings["manager_bot_token"])

            # Получаем список manager_chat_ids из таблицы project_managers
            manager_rows = await conn.fetch("""
                SELECT manager_chat_id FROM project_managers
                WHERE project_id = $1
            """, uuid.UUID(project_id))
            settings["manager_chat_ids"] = [r["manager_chat_id"] for r in manager_rows]

            logger.info("Project settings retrieved", extra={"project_id": project_id})
            return settings

    async def get_bot_token(self, project_id: str) -> Optional[str]:
        """
        Возвращает только bot_token для проекта (расшифрованный).
        
        Args:
            project_id: UUID проекта в строковом формате.
        
        Returns:
            Расшифрованный токен бота или None.
        """
        logger.info("Fetching bot token", extra={"project_id": project_id})
        async with self.pool.acquire() as conn:
            encrypted = await conn.fetchval("""
                SELECT bot_token FROM projects WHERE id = $1
            """, uuid.UUID(project_id))
            token = self._decrypt_if_present(encrypted)
            if token:
                logger.info("Bot token found", extra={"project_id": project_id})
            else:
                logger.warning("No bot token found", extra={"project_id": project_id})
            return token

    async def set_bot_token(self, project_id: str, token: str) -> None:
        """
        Устанавливает bot_token для проекта (шифрует перед сохранением).
        
        Args:
            project_id: UUID проекта в строковом формате.
            token: Токен бота для шифрования и сохранения.
        """
        logger.info("Setting bot token", extra={"project_id": project_id})
        encrypted = self._encrypt_if_present(token)
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE projects SET bot_token = $1, updated_at = NOW()
                WHERE id = $2
            """, encrypted, uuid.UUID(project_id))

    async def get_manager_bot_token(self, project_id: str) -> Optional[str]:
        """
        Возвращает manager_bot_token для проекта (расшифрованный).
        
        Args:
            project_id: UUID проекта в строковом формате.
        
        Returns:
            Расшифрованный токен менеджерского бота или None.
        """
        logger.info("Fetching manager bot token", extra={"project_id": project_id})
        async with self.pool.acquire() as conn:
            encrypted = await conn.fetchval("""
                SELECT manager_bot_token FROM projects WHERE id = $1
            """, uuid.UUID(project_id))
            token = self._decrypt_if_present(encrypted)
            if token:
                logger.info("Manager bot token found", extra={"project_id": project_id})
            else:
                logger.warning("No manager bot token found", extra={"project_id": project_id})
            return token

    async def set_manager_bot_token(self, project_id: str, token: str) -> None:
        """
        Устанавливает manager_bot_token для проекта (шифрует перед сохранением).
        
        Args:
            project_id: UUID проекта в строковом формате.
            token: Токен менеджерского бота для шифрования и сохранения.
        """
        logger.info("Setting manager bot token", extra={"project_id": project_id})
        encrypted = self._encrypt_if_present(token)
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE projects SET manager_bot_token = $1, updated_at = NOW()
                WHERE id = $2
            """, encrypted, uuid.UUID(project_id))

    async def get_webhook_secret(self, project_id: str) -> Optional[str]:
        """
        Возвращает webhook_secret для проекта.
        
        Args:
            project_id: UUID проекта в строковом формате.
        
        Returns:
            Webhook secret или None.
        """
        logger.debug("Fetching webhook secret", extra={"project_id": project_id})
        async with self.pool.acquire() as conn:
            secret = await conn.fetchval("""
                SELECT webhook_secret FROM projects WHERE id = $1
            """, uuid.UUID(project_id))
            return secret

    async def set_webhook_secret(self, project_id: str, secret: str) -> None:
        """
        Устанавливает webhook_secret для проекта.
        
        Args:
            project_id: UUID проекта в строковом формате.
            secret: Webhook secret для сохранения.
        """
        logger.info("Setting webhook secret", extra={"project_id": project_id})
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE projects SET webhook_secret = $1, updated_at = NOW()
                WHERE id = $2
            """, secret, uuid.UUID(project_id))

    # ------------------------------------------------------------------
    # Manager management
    # ------------------------------------------------------------------
    async def get_managers(self, project_id: str) -> List[str]:
        """
        Возвращает список manager_chat_id для проекта.
        
        Args:
            project_id: UUID проекта в строковом формате.
        
        Returns:
            Список chat_id менеджеров.
        """
        logger.debug("Fetching managers", extra={"project_id": project_id})
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT manager_chat_id FROM project_managers
                WHERE project_id = $1
            """, uuid.UUID(project_id))
            return [r["manager_chat_id"] for r in rows]

    async def add_manager(self, project_id: str, manager_chat_id: str) -> None:
        """
        Добавляет менеджера (chat_id) в список менеджеров проекта.
        Игнорирует дубликаты.
        
        Args:
            project_id: UUID проекта в строковом формате.
            manager_chat_id: Telegram chat_id менеджера.
        """
        logger.info("Adding manager", extra={"project_id": project_id, "manager_chat_id": manager_chat_id})
        async with self.pool.acquire() as conn:
            try:
                await conn.execute("""
                    INSERT INTO project_managers (project_id, manager_chat_id)
                    VALUES ($1, $2)
                """, uuid.UUID(project_id), manager_chat_id)
            except asyncpg.exceptions.UniqueViolationError:
                logger.warning(
                    "Manager already exists",
                    extra={"project_id": project_id, "manager_chat_id": manager_chat_id}
                )

    async def remove_manager(self, project_id: str, manager_chat_id: str) -> None:
        """
        Удаляет менеджера (chat_id) из списка менеджеров проекта.
        
        Args:
            project_id: UUID проекта в строковом формате.
            manager_chat_id: Telegram chat_id менеджера для удаления.
        """
        logger.info("Removing manager", extra={"project_id": project_id, "manager_chat_id": manager_chat_id})
        async with self.pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM project_managers
                WHERE project_id = $1 AND manager_chat_id = $2
            """, uuid.UUID(project_id), manager_chat_id)

    # ------------------------------------------------------------------
    # Template & Pro mode management (NEW)
    # ------------------------------------------------------------------
    async def apply_template(self, project_id: str, template_slug: str) -> bool:
        """
        Применяет шаблон воркфлоу к проекту.
        
        Устанавливает template_slug для проекта, что указывает оркестратору
        использовать предопределённый граф из workflow_templates.
        
        Args:
            project_id: UUID проекта в строковом формате.
            template_slug: Уникальный slug шаблона (например, 'support', 'leads').
        
        Returns:
            True если шаблон применён успешно, False если шаблон не найден.
        """
        logger.info(
            "Applying template to project",
            extra={"project_id": project_id, "template_slug": template_slug}
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
                    extra={"project_id": project_id, "template_slug": template_slug}
                )
                return False
            
            # Применяем шаблон
            await conn.execute("""
                UPDATE projects 
                SET template_slug = $1, updated_at = NOW()
                WHERE id = $2
            """, template_slug, uuid.UUID(project_id))
            
            logger.info(
                "Template applied successfully",
                extra={"project_id": project_id, "template_slug": template_slug}
            )
            return True

    async def set_pro_mode(self, project_id: str, enabled: bool) -> None:
        """
        Включает или отключает Pro mode для проекта.
        
        Pro mode даёт доступ к custom workflow canvas и расширенным функциям.
        
        Args:
            project_id: UUID проекта в строковом формате.
            enabled: True для включения Pro mode, False для отключения.
        """
        logger.info(
            "Setting pro mode",
            extra={"project_id": project_id, "enabled": enabled}
        )
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE projects 
                SET is_pro_mode = $1, updated_at = NOW()
                WHERE id = $2
            """, enabled, uuid.UUID(project_id))

    async def get_template_slug(self, project_id: str) -> Optional[str]:
        """
        Возвращает slug применённого шаблона для проекта.
        
        Args:
            project_id: UUID проекта в строковом формате.
        
        Returns:
            Slug шаблона или None если шаблон не применён.
        """
        logger.debug("Getting template slug", extra={"project_id": project_id})
        async with self.pool.acquire() as conn:
            slug = await conn.fetchval(
                "SELECT template_slug FROM projects WHERE id = $1",
                uuid.UUID(project_id)
            )
            return slug

    async def get_is_pro_mode(self, project_id: str) -> bool:
        """
        Проверяет, включён ли Pro mode для проекта.
        
        Args:
            project_id: UUID проекта в строковом формате.
        
        Returns:
            True если Pro mode включён, False иначе.
        """
        logger.debug("Checking pro mode", extra={"project_id": project_id})
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT is_pro_mode FROM projects WHERE id = $1",
                uuid.UUID(project_id)
            )
            return bool(result)

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    async def project_exists(self, project_id: str) -> bool:
        """
        Проверяет, существует ли проект с указанным ID.
        
        Args:
            project_id: UUID проекта в строковом формате.
        
        Returns:
            True если проект существует, False иначе.
        """
        logger.debug("Checking project existence", extra={"project_id": project_id})
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT 1 FROM projects WHERE id = $1", 
                uuid.UUID(project_id)
            )
            return result is not None
