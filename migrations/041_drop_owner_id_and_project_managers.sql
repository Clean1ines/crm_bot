-- Migration 041: Drop legacy ownership and Telegram-only manager storage.
--
-- Preconditions:
-- - projects.user_id is populated for owned projects.
-- - project_members contains owner/admin/manager rows.
-- - migration 040 has backfilled linked Telegram managers.

DROP TABLE IF EXISTS project_managers;

ALTER TABLE projects
    DROP COLUMN IF EXISTS owner_id;
