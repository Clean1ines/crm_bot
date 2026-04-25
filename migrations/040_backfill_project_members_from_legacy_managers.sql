-- Migration 040: Backfill canonical manager memberships from legacy project_managers.
--
-- This is intentionally separate from 037 so environments that already applied
-- 037 before the improved backfill still get the canonical membership data.

INSERT INTO project_members (project_id, user_id, role)
SELECT pm.project_id, ai.user_id, 'manager'
FROM project_managers pm
JOIN auth_identities ai
  ON ai.provider = 'telegram'
 AND ai.provider_id = pm.manager_chat_id
ON CONFLICT (project_id, user_id) DO NOTHING;

INSERT INTO project_members (project_id, user_id, role)
SELECT pm.project_id, u.id, 'manager'
FROM project_managers pm
JOIN users u
  ON CAST(u.telegram_id AS TEXT) = pm.manager_chat_id
WHERE u.telegram_id IS NOT NULL
ON CONFLICT (project_id, user_id) DO NOTHING;
