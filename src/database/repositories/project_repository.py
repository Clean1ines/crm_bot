import uuid
from typing import Optional, Dict, Any
from src.core.logging import get_logger

logger = get_logger(__name__)

class ProjectRepository:
    def __init__(self, pool):
        """
        Принимает пул соединений asyncpg.
        """
        self.pool = pool

    async def get_project_settings(self, project_id: str) -> Dict[str, Any]:
        """
        Возвращает настройки проекта (system_prompt, bot_token, webhook_url и т.д.).
        Если проект не найден, возвращает пустой словарь.
        """
        logger.info(f"Fetching project settings for project {project_id}")
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT system_prompt, bot_token, webhook_url
                FROM projects
                WHERE id = $1
            """, uuid.UUID(project_id))
            if not row:
                logger.warning(f"Project {project_id} not found")
                return {}
            settings = dict(row)
            logger.info(f"Project settings retrieved for {project_id}")
            return settings

    async def get_bot_token(self, project_id: str) -> Optional[str]:
        """
        Возвращает только bot_token для проекта.
        """
        logger.info(f"Fetching bot token for project {project_id}")
        async with self.pool.acquire() as conn:
            token = await conn.fetchval("""
                SELECT bot_token FROM projects WHERE id = $1
            """, uuid.UUID(project_id))
            if token:
                logger.info(f"Bot token found for project {project_id}")
            else:
                logger.warning(f"No bot token found for project {project_id}")
            return token
