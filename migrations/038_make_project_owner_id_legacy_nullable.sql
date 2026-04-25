-- Migration 038: Demote projects.owner_id to nullable legacy bridge.
--
-- Canonical ownership is projects.user_id plus project_members(project_id, user_id, role).
-- owner_id remains temporarily for old Telegram-created rows and compatibility-only
-- code paths, but new domain code must not write or read it as ownership source.

ALTER TABLE projects
    ALTER COLUMN owner_id DROP NOT NULL;

COMMENT ON COLUMN projects.owner_id IS
    'Legacy bridge only. Canonical project ownership is projects.user_id and project_members.';
