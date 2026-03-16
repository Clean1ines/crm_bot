import uuid
from typing import Optional, Dict, Any, List
from src.core.logging import get_logger
from src.utils.encryption import encrypt_token, decrypt_token

logger = get_logger(__name__)

class ProjectRepository:
    def __init__(self, pool):
        """
        Принимает пул соединений asyncpg.
        """
        self.pool = pool

    # ------------------------------------------------------------------
    # Private helpers to encrypt/decrypt token fields
    # ------------------------------------------------------------------
    def _encrypt_if_present(self, token: Optional[str]) -> Optional[str]:
        return encrypt_token(token) if token else None

    def _decrypt_if_present(self, encrypted: Optional[str]) -> Optional[str]:
        return decrypt_token(encrypted) if encrypted else None

    # ------------------------------------------------------------------
    # Public methods
    # ------------------------------------------------------------------
    async def get_project_settings(self, project_id: str) -> Dict[str, Any]:
        """
        Возвращает настройки проекта: system_prompt, bot_token, webhook_url,
        manager_bot_token, webhook_secret и список manager_chat_ids.
        Если проект не найден, возвращает пустой словарь.
        """
        logger.info(f"Fetching project settings for project {project_id}")
        async with self.pool.acquire() as conn:
            # Получаем основные поля проекта
            row = await conn.fetchrow("""
                SELECT system_prompt, bot_token, webhook_url, manager_bot_token, webhook_secret
                FROM projects
                WHERE id = $1
            """, uuid.UUID(project_id))
            if not row:
                logger.warning(f"Project {project_id} not found")
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

            logger.info(f"Project settings retrieved for {project_id}")
            return settings

    async def get_bot_token(self, project_id: str) -> Optional[str]:
        """
        Возвращает только bot_token для проекта (расшифрованный).
        """
        logger.info(f"Fetching bot token for project {project_id}")
        async with self.pool.acquire() as conn:
            encrypted = await conn.fetchval("""
                SELECT bot_token FROM projects WHERE id = $1
            """, uuid.UUID(project_id))
            token = self._decrypt_if_present(encrypted)
            if token:
                logger.info(f"Bot token found for project {project_id}")
            else:
                logger.warning(f"No bot token found for project {project_id}")
            return token

    async def set_bot_token(self, project_id: str, token: str) -> None:
        """
        Устанавливает bot_token для проекта (шифрует перед сохранением).
        """
        logger.info(f"Setting bot token for project {project_id}")
        encrypted = self._encrypt_if_present(token)
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE projects SET bot_token = $1, updated_at = NOW()
                WHERE id = $2
            """, encrypted, uuid.UUID(project_id))

    async def get_manager_bot_token(self, project_id: str) -> Optional[str]:
        """
        Возвращает manager_bot_token для проекта (расшифрованный).
        """
        logger.info(f"Fetching manager bot token for project {project_id}")
        async with self.pool.acquire() as conn:
            encrypted = await conn.fetchval("""
                SELECT manager_bot_token FROM projects WHERE id = $1
            """, uuid.UUID(project_id))
            token = self._decrypt_if_present(encrypted)
            if token:
                logger.info(f"Manager bot token found for project {project_id}")
            else:
                logger.warning(f"No manager bot token found for project {project_id}")
            return token

    async def set_manager_bot_token(self, project_id: str, token: str) -> None:
        """
        Устанавливает manager_bot_token для проекта (шифрует перед сохранением).
        """
        logger.info(f"Setting manager bot token for project {project_id}")
        encrypted = self._encrypt_if_present(token)
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE projects SET manager_bot_token = $1, updated_at = NOW()
                WHERE id = $2
            """, encrypted, uuid.UUID(project_id))

    async def get_webhook_secret(self, project_id: str) -> Optional[str]:
        """
        Возвращает webhook_secret для проекта.
        """
        logger.debug(f"Fetching webhook secret for project {project_id}")
        async with self.pool.acquire() as conn:
            secret = await conn.fetchval("""
                SELECT webhook_secret FROM projects WHERE id = $1
            """, uuid.UUID(project_id))
            return secret

    async def set_webhook_secret(self, project_id: str, secret: str) -> None:
        """
        Устанавливает webhook_secret для проекта.
        """
        logger.info(f"Setting webhook secret for project {project_id}")
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE projects SET webhook_secret = $1, updated_at = NOW()
                WHERE id = $2
            """, secret, uuid.UUID(project_id))

    async def get_managers(self, project_id: str) -> List[str]:
        """
        Возвращает список manager_chat_id для проекта.
        """
        logger.debug(f"Fetching managers for project {project_id}")
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
        """
        logger.info(f"Adding manager {manager_chat_id} to project {project_id}")
        async with self.pool.acquire() as conn:
            try:
                await conn.execute("""
                    INSERT INTO project_managers (project_id, manager_chat_id)
                    VALUES ($1, $2)
                """, uuid.UUID(project_id), manager_chat_id)
            except asyncpg.exceptions.UniqueViolationError:
                logger.warning(f"Manager {manager_chat_id} already exists for project {project_id}")

    async def remove_manager(self, project_id: str, manager_chat_id: str) -> None:
        """
        Удаляет менеджера (chat_id) из списка менеджеров проекта.
        """
        logger.info(f"Removing manager {manager_chat_id} from project {project_id}")
        async with self.pool.acquire() as conn:
            await conn.execute("""
                DELETE FROM project_managers
                WHERE project_id = $1 AND manager_chat_id = $2
            """, uuid.UUID(project_id), manager_chat_id)
