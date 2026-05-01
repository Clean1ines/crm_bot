"""
Project membership and manager identity operations.
"""

from src.domain.display_names import build_display_name
from src.domain.control_plane.project_views import (
    ManagerMembershipMutationView,
    ProjectMemberView,
)
from src.domain.project_plane.manager_notifications import ManagerNotificationTarget

from .base import ProjectRepositoryBase, ProjectId, ensure_uuid, logger


class ProjectMemberRepository(ProjectRepositoryBase):
    async def get_manager_notification_targets(
        self, project_id: ProjectId
    ) -> list[str]:
        targets = await self.get_manager_notification_recipients(project_id)
        telegram_chat_ids = [target.telegram_chat_id for target in targets]
        return telegram_chat_ids

    async def get_manager_notification_recipients(
        self,
        project_id: ProjectId,
    ) -> list[ManagerNotificationTarget]:
        logger.debug(
            "Fetching manager notification targets",
            extra={"project_id": str(project_id)},
        )
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT
                    pm.user_id,
                    CAST(u.telegram_id AS TEXT) AS manager_chat_id
                FROM project_members pm
                JOIN users u ON u.id = pm.user_id
                WHERE pm.project_id = $1
                  AND pm.role IN ('owner', 'admin', 'manager')
                  AND u.telegram_id IS NOT NULL
            """,
                ensure_uuid(project_id),
            )

        recipients = [
            ManagerNotificationTarget(
                user_id=str(r["user_id"]) if r.get("user_id") is not None else None,
                telegram_chat_id=str(r["manager_chat_id"]),
            )
            for r in rows
            if r.get("manager_chat_id") is not None
        ]
        return recipients

    async def add_manager_by_telegram_identity(
        self,
        project_id: ProjectId,
        manager_chat_id: str,
    ) -> ManagerMembershipMutationView:
        project_uuid = ensure_uuid(project_id)

        async with self.pool.acquire() as conn:
            user_row = await conn.fetchrow(
                """
                SELECT id
                FROM users
                WHERE telegram_id = $1
            """,
                int(manager_chat_id),
            )

            if user_row:
                user_id = user_row["id"]
            else:
                user_id = await conn.fetchval(
                    """
                    INSERT INTO users (id, telegram_id, full_name)
                    VALUES (gen_random_uuid(), $1, $2)
                    RETURNING id
                """,
                    int(manager_chat_id),
                    "",
                )

                await conn.execute(
                    """
                    INSERT INTO auth_identities (user_id, provider, provider_id)
                    VALUES ($1, 'telegram', $2)
                    ON CONFLICT (provider, provider_id) DO NOTHING
                """,
                    user_id,
                    manager_chat_id,
                )

            await conn.execute(
                """
                INSERT INTO project_members (project_id, user_id, role)
                VALUES ($1, $2, 'manager')
                ON CONFLICT (project_id, user_id)
                DO UPDATE SET role = CASE
                    WHEN project_members.role = 'owner' THEN project_members.role
                    ELSE EXCLUDED.role
                END
            """,
                project_uuid,
                user_id,
            )
        self._invalidate_project_runtime_cache(project_id)

        return ManagerMembershipMutationView(
            status="added",
            storage="project_members",
            user_id=str(user_id),
            role="manager",
        )

    async def remove_manager_by_telegram_identity(
        self,
        project_id: ProjectId,
        manager_chat_id: str,
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                DELETE FROM project_members pm
                USING users u
                WHERE pm.project_id = $1
                  AND pm.user_id = u.id
                  AND u.telegram_id = $2
                  AND pm.role = 'manager'
            """,
                ensure_uuid(project_id),
                int(manager_chat_id),
            )
        self._invalidate_project_runtime_cache(project_id)

    async def resolve_manager_user_id_by_telegram(
        self,
        project_id: ProjectId,
        manager_chat_id: str,
    ) -> str | None:
        async with self.pool.acquire() as conn:
            user_id = await conn.fetchval(
                """
                SELECT u.id
                FROM project_members pm
                JOIN users u ON u.id = pm.user_id
                LEFT JOIN auth_identities ai
                    ON ai.user_id = u.id
                   AND ai.provider = 'telegram'
                WHERE pm.project_id = $1
                  AND pm.role IN ('owner', 'admin', 'manager')
                  AND (
                      u.telegram_id = $2
                      OR ai.provider_id = $3
                  )
                LIMIT 1
            """,
                ensure_uuid(project_id),
                int(manager_chat_id),
                str(manager_chat_id),
            )

        return str(user_id) if user_id else None

    async def get_user_display_name(self, user_id: ProjectId) -> str | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT full_name, username, email
                FROM users
                WHERE id = $1
            """,
                ensure_uuid(user_id),
            )

        if not row:
            return None
        return build_display_name(
            full_name=row["full_name"],
            username=row["username"],
            email=row["email"],
            fallback="Менеджер",
        )

    async def get_project_members_view(
        self, project_id: ProjectId
    ) -> list[ProjectMemberView]:
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                WITH owner_member AS (
                    SELECT
                        p.user_id AS id,
                        p.id AS project_id,
                        p.user_id,
                        'owner'::varchar AS role,
                        p.created_at,
                        u.telegram_id,
                        u.username,
                        u.full_name,
                        u.email
                    FROM projects p
                    JOIN users u ON u.id = p.user_id
                    WHERE p.id = $1
                      AND p.user_id IS NOT NULL
                      AND NOT EXISTS (
                          SELECT 1
                          FROM project_members pm
                          WHERE pm.project_id = p.id
                            AND pm.user_id = p.user_id
                      )
                )
                SELECT *
                FROM (
                    SELECT
                        pm.id,
                        pm.project_id,
                        pm.user_id,
                        pm.role,
                        pm.created_at,
                        u.telegram_id,
                        u.username,
                        u.full_name,
                        u.email
                    FROM project_members pm
                    JOIN users u ON u.id = pm.user_id
                    WHERE pm.project_id = $1

                    UNION ALL

                    SELECT *
                    FROM owner_member
                ) members
                ORDER BY members.created_at ASC
            """,
                ensure_uuid(project_id),
            )

        members: list[ProjectMemberView] = []
        for row in rows:
            member = dict(row)
            member["project_id"] = str(member["project_id"])
            member["user_id"] = str(member["user_id"])
            if member.get("telegram_id") is not None:
                member["telegram_id"] = int(member["telegram_id"])
            members.append(ProjectMemberView.from_record(member))
        return members

    async def add_project_member(
        self, project_id: ProjectId, user_id: ProjectId, role: str
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO project_members (project_id, user_id, role)
                VALUES ($1, $2, $3)
                ON CONFLICT (project_id, user_id)
                DO UPDATE SET role = EXCLUDED.role
            """,
                ensure_uuid(project_id),
                ensure_uuid(user_id),
                role,
            )

    async def remove_project_member(
        self, project_id: ProjectId, user_id: ProjectId
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                DELETE FROM project_members
                WHERE project_id = $1 AND user_id = $2
            """,
                ensure_uuid(project_id),
                ensure_uuid(user_id),
            )

    async def get_project_member_role(
        self, project_id: ProjectId, user_id: ProjectId
    ) -> str | None:
        async with self.pool.acquire() as conn:
            role = await conn.fetchval(
                """
                SELECT role
                FROM project_members
                WHERE project_id = $1 AND user_id = $2
            """,
                ensure_uuid(project_id),
                ensure_uuid(user_id),
            )

        return str(role) if role else None
