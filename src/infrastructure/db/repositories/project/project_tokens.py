"""
Token and webhook-secret operations for projects.
"""

from typing import Optional

from .base import ProjectRepositoryBase, ProjectId, ensure_uuid, logger


class ProjectTokenRepository(ProjectRepositoryBase):
    async def get_bot_token(self, project_id: ProjectId) -> Optional[str]:
        logger.info("Fetching bot token", extra={"project_id": str(project_id)})
        async with self.pool.acquire() as conn:
            encrypted = await conn.fetchval("""
                SELECT bot_token FROM projects WHERE id = $1
            """, ensure_uuid(project_id))
            return self._decrypt_if_present(encrypted)

    async def set_bot_token(self, project_id: ProjectId, token: Optional[str]) -> None:
        logger.info("Setting bot token", extra={"project_id": str(project_id)})
        encrypted = self._encrypt_if_present(token)
        username = await self._get_bot_username(token) if token else None

        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE projects 
                SET bot_token = $1, client_bot_username = $2, updated_at = NOW()
                WHERE id = $3
            """, encrypted, username, ensure_uuid(project_id))

    async def get_manager_bot_token(self, project_id: ProjectId) -> Optional[str]:
        logger.info("Fetching manager bot token", extra={"project_id": str(project_id)})
        async with self.pool.acquire() as conn:
            encrypted = await conn.fetchval("""
                SELECT manager_bot_token FROM projects WHERE id = $1
            """, ensure_uuid(project_id))
            return self._decrypt_if_present(encrypted)

    async def set_manager_bot_token(self, project_id: ProjectId, token: Optional[str]) -> None:
        logger.info("Setting manager bot token", extra={"project_id": str(project_id)})
        encrypted = self._encrypt_if_present(token)
        username = await self._get_bot_username(token) if token else None

        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE projects 
                SET manager_bot_token = $1, manager_bot_username = $2, updated_at = NOW()
                WHERE id = $3
            """, encrypted, username, ensure_uuid(project_id))

    async def get_webhook_secret(self, project_id: ProjectId) -> Optional[str]:
        async with self.pool.acquire() as conn:
            return await conn.fetchval("""
                SELECT webhook_secret FROM projects WHERE id = $1
            """, ensure_uuid(project_id))

    async def set_webhook_secret(self, project_id: ProjectId, secret: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE projects SET webhook_secret = $1, updated_at = NOW()
                WHERE id = $2
            """, secret, ensure_uuid(project_id))

    async def get_manager_webhook_secret(self, project_id: ProjectId) -> Optional[str]:
        async with self.pool.acquire() as conn:
            return await conn.fetchval("""
                SELECT manager_webhook_secret FROM projects WHERE id = $1
            """, ensure_uuid(project_id))

    async def set_manager_webhook_secret(self, project_id: ProjectId, secret: str) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE projects SET manager_webhook_secret = $1, updated_at = NOW()
                WHERE id = $2
            """, secret, ensure_uuid(project_id))

    async def find_project_by_manager_webhook_secret(self, secret: str) -> Optional[str]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id FROM projects WHERE manager_webhook_secret = $1
            """, secret)
            return str(row["id"]) if row else None

    async def find_project_by_manager_token(self, raw_token: str) -> Optional[str]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, manager_bot_token FROM projects WHERE manager_bot_token IS NOT NULL"
            )
            for row in rows:
                decrypted = self._decrypt_if_present(row["manager_bot_token"])
                if decrypted == raw_token:
                    return str(row["id"])
        return None
