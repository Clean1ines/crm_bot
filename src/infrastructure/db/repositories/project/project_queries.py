"""
Core project query operations.
"""

from typing import Optional

from src.domain.control_plane.project_views import ProjectSummaryView

from .base import ProjectRepositoryBase, JsonList, JsonMap, ProjectId, ensure_uuid, logger


class ProjectQueryRepository(ProjectRepositoryBase):
    async def get_project_settings(self, project_id: ProjectId) -> JsonMap:
        logger.info("Fetching project settings", extra={"project_id": str(project_id)})

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT system_prompt, bot_token, webhook_url, manager_bot_token, 
                       webhook_secret, is_pro_mode,
                       client_bot_username, manager_bot_username
                FROM projects
                WHERE id = $1
            """, ensure_uuid(project_id))

            if not row:
                logger.warning("Project not found", extra={"project_id": str(project_id)})
                return {}

            project_settings = dict(row)
            project_settings["bot_token"] = self._decrypt_if_present(project_settings["bot_token"])
            project_settings["manager_bot_token"] = self._decrypt_if_present(project_settings["manager_bot_token"])

            manager_rows = await conn.fetch("""
                SELECT CAST(u.telegram_id AS TEXT) AS manager_chat_id
                FROM project_members pm
                JOIN users u ON u.id = pm.user_id
                WHERE pm.project_id = $1
                  AND pm.role IN ('owner', 'admin', 'manager')
                  AND u.telegram_id IS NOT NULL
            """, ensure_uuid(project_id))

        targets = [
            str(r.get("manager_chat_id") if r.get("manager_chat_id") is not None else r.get("telegram_id"))
            for r in manager_rows
            if r.get("manager_chat_id") is not None or r.get("telegram_id") is not None
        ]
        project_settings["manager_notification_targets"] = targets
        project_settings["manager_chat_ids"] = targets
        return project_settings

    async def get_all_projects(self) -> JsonList:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, user_id, name, is_pro_mode, created_at, updated_at
                FROM projects
                ORDER BY created_at DESC
            """)

        projects = []
        for row in rows:
            project = dict(row)
            project["id"] = str(project["id"])
            if project.get("user_id"):
                project["user_id"] = str(project["user_id"])
            projects.append(project)
        return projects

    async def get_project_view(self, project_id: ProjectId) -> Optional[ProjectSummaryView]:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT id, user_id, name, is_pro_mode, created_at, updated_at,
                       client_bot_username, manager_bot_username
                FROM projects
                WHERE id = $1
            """, ensure_uuid(project_id))

        if not row:
            return None

        project = dict(row)
        project["id"] = str(project["id"])
        if project.get("user_id"):
            project["user_id"] = str(project["user_id"])
        return ProjectSummaryView.from_record(project)

    async def get_projects_by_user_id(self, user_id: str) -> JsonList:
        logger.info("Fetching projects by user_id", extra={"user_id": user_id})
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT id, name, is_pro_mode, created_at, updated_at,
                       client_bot_username, manager_bot_username
                FROM projects
                WHERE user_id = $1
                ORDER BY created_at DESC
            """, user_id)

        projects = []
        for row in rows:
            project = dict(row)
            project["id"] = str(project["id"])
            project["user_id"] = user_id
            projects.append(project)
        return projects

    async def get_projects_for_user_view(self, user_id: str) -> list[ProjectSummaryView]:
        logger.info("Fetching projects for user", extra={"user_id": user_id})
        async with self.pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT DISTINCT ON (p.id)
                    p.id, p.name, p.is_pro_mode, p.created_at, p.updated_at,
                    p.client_bot_username, p.manager_bot_username, p.user_id,
                    CASE
                        WHEN p.user_id = $1 THEN 'owner'
                        ELSE pm.role
                    END AS access_role
                FROM projects p
                LEFT JOIN project_members pm
                    ON pm.project_id = p.id AND pm.user_id = $1
                WHERE p.user_id = $1 OR pm.user_id = $1
                ORDER BY p.id, p.created_at DESC
            """, user_id)

        projects: list[ProjectSummaryView] = []
        for row in rows:
            project = dict(row)
            project["id"] = str(project["id"])
            if project.get("user_id"):
                project["user_id"] = str(project["user_id"])
            projects.append(ProjectSummaryView.from_record(project))
        return projects

    async def user_has_project_role(
        self,
        project_id: ProjectId,
        user_id: ProjectId,
        allowed_roles: Optional[list[str]] = None,
    ) -> bool:
        allowed_roles = allowed_roles or ["owner", "admin", "manager", "viewer"]

        project = await self.get_project_view(project_id)
        if not project:
            return False

        if project.user_id == str(user_id):
            return True

        role = await self.get_project_member_role(project_id, user_id)
        return role in allowed_roles
