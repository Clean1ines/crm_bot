import uuid
from typing import Optional, Dict, Any

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
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT system_prompt, bot_token, webhook_url
                FROM projects
                WHERE id = $1
            """, uuid.UUID(project_id))
            if not row:
                return {}
            return dict(row)

    async def get_bot_token(self, project_id: str) -> Optional[str]:
        """
        Возвращает только bot_token для проекта.
        """
        async with self.pool.acquire() as conn:
            token = await conn.fetchval("""
                SELECT bot_token FROM projects WHERE id = $1
            """, uuid.UUID(project_id))
            return token
