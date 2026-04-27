"""
Project channel command operations.
"""

import json
from typing import Optional

from src.domain.control_plane.project_configuration import ProjectChannelView

from .base import JsonMap, ProjectId, ProjectRepositoryBase, ensure_uuid


class ProjectChannelRepository(ProjectRepositoryBase):
    async def upsert_project_channel(
        self,
        project_id: ProjectId,
        kind: str,
        provider: str,
        status: str,
        config_json: Optional[JsonMap] = None,
    ) -> ProjectChannelView:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                INSERT INTO project_channels (
                    project_id, kind, provider, status, config_json
                )
                VALUES ($1, $2, $3, $4, COALESCE($5::jsonb, '{}'::jsonb))
                ON CONFLICT (project_id, kind, provider)
                DO UPDATE SET
                    status = EXCLUDED.status,
                    config_json = EXCLUDED.config_json,
                    updated_at = NOW()
                RETURNING id, project_id, kind, provider, status, config_json, created_at, updated_at
                """,
                ensure_uuid(project_id),
                kind,
                provider,
                status,
                json.dumps(config_json or {}, ensure_ascii=False),
            )

        return ProjectChannelView.from_record(self._normalize_record(row))
