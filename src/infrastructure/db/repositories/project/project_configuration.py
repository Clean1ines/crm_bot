"""
Project configuration read/write operations.
"""

from src.domain.control_plane.project_configuration import ProjectConfigurationView

from .base import ProjectRepositoryBase, JsonMap, ProjectId, ensure_uuid


class ProjectConfigurationRepository(ProjectRepositoryBase):
    async def get_project_configuration_view(
        self, project_id: ProjectId
    ) -> ProjectConfigurationView:
        project_uuid = ensure_uuid(project_id)

        async with self.pool.acquire() as conn:
            settings_row = await conn.fetchrow(
                """
                SELECT brand_name, industry, tone_of_voice, default_language,
                       default_timezone, system_prompt_override, created_at, updated_at
                FROM project_settings
                WHERE project_id = $1
            """,
                project_uuid,
            )

            policies_row = await conn.fetchrow(
                """
                SELECT escalation_policy_json, routing_policy_json, crm_policy_json,
                       response_policy_json, privacy_policy_json, created_at, updated_at
                FROM project_policies
                WHERE project_id = $1
            """,
                project_uuid,
            )

            limit_row = await conn.fetchrow(
                """
                SELECT monthly_token_limit, requests_per_minute, max_concurrent_threads,
                       priority, fallback_model, created_at, updated_at
                FROM project_limit_profiles
                WHERE project_id = $1
            """,
                project_uuid,
            )

            integrations_rows = await conn.fetch(
                """
                SELECT id, provider, status, config_json, created_at, updated_at
                FROM project_integrations
                WHERE project_id = $1
                ORDER BY created_at ASC
            """,
                project_uuid,
            )

            channels_rows = await conn.fetch(
                """
                SELECT id, kind, provider, status, config_json, created_at, updated_at
                FROM project_channels
                WHERE project_id = $1
                ORDER BY created_at ASC
            """,
                project_uuid,
            )

            prompt_rows = await conn.fetch(
                """
                SELECT id, name, prompt_json, version, is_active, created_at, updated_at
                FROM project_prompt_versions
                WHERE project_id = $1
                ORDER BY version DESC, created_at DESC
            """,
                project_uuid,
            )

        return ProjectConfigurationView.from_record(
            {
                "project_id": str(project_uuid),
                "settings": self._normalize_record(settings_row),
                "policies": self._normalize_record(policies_row),
                "limit_profile": self._normalize_record(limit_row),
                "integrations": [
                    self._normalize_record(row) for row in integrations_rows
                ],
                "channels": [self._normalize_record(row) for row in channels_rows],
                "prompt_versions": [
                    {
                        **self._normalize_record(row),
                        "prompt_bundle": self._normalize_record(row).get(
                            "prompt_json", {}
                        ),
                    }
                    for row in prompt_rows
                ],
            }
        )

    async def update_project_settings(
        self, project_id: ProjectId, data: JsonMap
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO project_settings (
                    project_id, brand_name, industry, tone_of_voice,
                    default_language, default_timezone, system_prompt_override
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (project_id)
                DO UPDATE SET
                    brand_name = COALESCE(EXCLUDED.brand_name, project_settings.brand_name),
                    industry = COALESCE(EXCLUDED.industry, project_settings.industry),
                    tone_of_voice = COALESCE(EXCLUDED.tone_of_voice, project_settings.tone_of_voice),
                    default_language = COALESCE(EXCLUDED.default_language, project_settings.default_language),
                    default_timezone = COALESCE(EXCLUDED.default_timezone, project_settings.default_timezone),
                    system_prompt_override = COALESCE(EXCLUDED.system_prompt_override, project_settings.system_prompt_override),
                    updated_at = NOW()
            """,
                ensure_uuid(project_id),
                data.get("brand_name"),
                data.get("industry"),
                data.get("tone_of_voice"),
                data.get("default_language"),
                data.get("default_timezone"),
                data.get("system_prompt_override"),
            )
        self._invalidate_project_runtime_cache(project_id)

    async def update_project_policies(
        self, project_id: ProjectId, data: JsonMap
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO project_policies (
                    project_id, escalation_policy_json, routing_policy_json,
                    crm_policy_json, response_policy_json, privacy_policy_json
                )
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (project_id)
                DO UPDATE SET
                    escalation_policy_json = COALESCE(EXCLUDED.escalation_policy_json, project_policies.escalation_policy_json),
                    routing_policy_json = COALESCE(EXCLUDED.routing_policy_json, project_policies.routing_policy_json),
                    crm_policy_json = COALESCE(EXCLUDED.crm_policy_json, project_policies.crm_policy_json),
                    response_policy_json = COALESCE(EXCLUDED.response_policy_json, project_policies.response_policy_json),
                    privacy_policy_json = COALESCE(EXCLUDED.privacy_policy_json, project_policies.privacy_policy_json),
                    updated_at = NOW()
            """,
                ensure_uuid(project_id),
                data.get("escalation_policy_json"),
                data.get("routing_policy_json"),
                data.get("crm_policy_json"),
                data.get("response_policy_json"),
                data.get("privacy_policy_json"),
            )
        self._invalidate_project_runtime_cache(project_id)

    async def update_project_limit_profile(
        self, project_id: ProjectId, data: JsonMap
    ) -> None:
        async with self.pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO project_limit_profiles (
                    project_id, monthly_token_limit, requests_per_minute,
                    max_concurrent_threads, priority, fallback_model
                )
                VALUES ($1, $2, $3, $4, COALESCE($5, 0), $6)
                ON CONFLICT (project_id)
                DO UPDATE SET
                    monthly_token_limit = COALESCE(EXCLUDED.monthly_token_limit, project_limit_profiles.monthly_token_limit),
                    requests_per_minute = COALESCE(EXCLUDED.requests_per_minute, project_limit_profiles.requests_per_minute),
                    max_concurrent_threads = COALESCE(EXCLUDED.max_concurrent_threads, project_limit_profiles.max_concurrent_threads),
                    priority = COALESCE(EXCLUDED.priority, project_limit_profiles.priority),
                    fallback_model = COALESCE(EXCLUDED.fallback_model, project_limit_profiles.fallback_model),
                    updated_at = NOW()
            """,
                ensure_uuid(project_id),
                data.get("monthly_token_limit"),
                data.get("requests_per_minute"),
                data.get("max_concurrent_threads"),
                data.get("priority"),
                data.get("fallback_model"),
            )
        self._invalidate_project_runtime_cache(project_id)
