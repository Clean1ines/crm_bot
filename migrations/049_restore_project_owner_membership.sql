-- Migration 049: Restore canonical owner membership from projects.user_id.
--
-- project_members has one row per (project_id, user_id). Older manager-add flows
-- could overwrite role='owner' with role='manager'. This migration restores the
-- canonical owner role from projects.user_id and inserts a missing owner row.

UPDATE project_members pm
SET role = 'owner'
FROM projects p
WHERE pm.project_id = p.id
  AND pm.user_id = p.user_id
  AND p.user_id IS NOT NULL
  AND pm.role <> 'owner';

INSERT INTO project_members (project_id, user_id, role)
SELECT p.id, p.user_id, 'owner'
FROM projects p
WHERE p.user_id IS NOT NULL
  AND NOT EXISTS (
      SELECT 1
      FROM project_members pm
      WHERE pm.project_id = p.id
        AND pm.user_id = p.user_id
  );
