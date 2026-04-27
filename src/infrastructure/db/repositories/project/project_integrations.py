"""
Project integration command operations.
"""

from typing import Optional

from src.domain.control_plane.project_configuration import ProjectIntegrationView

from .base import JsonMap, ProjectId, ProjectRepositoryBase, ensure_uuid


class ProjectIntegrationRepository(ProjectRepositoryBase):
    async def upsert_project_integration(
        self,
        project_id: ProjectId,
        provider: str,
        status: str,
        config_json: Optional[JsonMap] = None,
        credentials_encrypted: Optional[str] = None,
    ) -> ProjectIntegrationView:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO project_integrations (
                    project_id, provider, status, credentials_encrypted, config_json
                )
                VALUES ($1, $2, $3, $4, COALESCE($5, '{}'::jsonb))
                ON CONFLICT (project_id, provider)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    credentials_encrypted = COALESCE(EXCLUDED.credentials_encrypted, project_integrations.credentials_encrypted),
                    config_json = EXCLUDED.config_json,
                    updated_at = NOW()
                RETURNING id, project_id, provider, status, config_json, credentials_encrypted, created_at, updated_at
                """,
                ensure_uuid(project_id),
                provider,
                status,
                credentials_encrypted,
                config_json or {},
            )

        return ProjectIntegrationView.from_record(self._normalize_record(row))
