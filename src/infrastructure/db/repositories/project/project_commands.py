"""
Core project command operations.
"""

from .base import ProjectRepositoryBase, ProjectId, ensure_uuid, logger


class ProjectCommandRepository(ProjectRepositoryBase):
    async def set_pro_mode(self, project_id: ProjectId, enabled: bool) -> None:
        logger.info(
            "Setting pro mode",
            extra={"project_id": str(project_id), "enabled": enabled},
        )
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE projects 
                SET is_pro_mode = $1, updated_at = NOW()
                WHERE id = $2
            """,
                enabled,
                ensure_uuid(project_id),
            )
        self._invalidate_project_runtime_cache(project_id)

    async def get_is_pro_mode(self, project_id: ProjectId) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT is_pro_mode FROM projects WHERE id = $1",
                ensure_uuid(project_id),
            )
        return bool(result)

    async def project_exists(self, project_id: ProjectId) -> bool:
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                "SELECT 1 FROM projects WHERE id = $1",
                ensure_uuid(project_id),
            )
        return result is not None

    async def create_project_with_user_id(self, user_id: str, name: str) -> str:
        logger.info(
            "Creating project with user_id", extra={"user_id": user_id, "name": name}
        )
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                project_id = await conn.fetchval(
                    """
                    INSERT INTO projects (id, name, user_id, bot_token, system_prompt)
                    VALUES (gen_random_uuid(), $1, $2, '', 'Ты — полезный AI-ассистент.')
                    RETURNING id
                """,
                    name,
                    user_id,
                )

                await conn.execute(
                    """
                    INSERT INTO project_members (project_id, user_id, role)
                    VALUES ($1, $2, 'owner')
                    ON CONFLICT (project_id, user_id)
                    DO UPDATE SET role = EXCLUDED.role
                """,
                    project_id,
                    ensure_uuid(user_id),
                )

        return str(project_id)

    async def update_project(self, project_id: ProjectId, name: str | None) -> None:
        if name is None:
            return

        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE projects SET name = $1, updated_at = NOW()
                WHERE id = $2
            """,
                name,
                ensure_uuid(project_id),
            )
        self._invalidate_project_runtime_cache(project_id)

    async def delete_project(self, project_id: ProjectId) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM projects WHERE id = $1", ensure_uuid(project_id)
            )
        self._invalidate_project_runtime_cache(project_id)
