-- Migration 039: Remove users.project_id inversion.
--
-- users are global platform identities. Project access belongs in
-- project_members(project_id, user_id, role), and CRM/customer context belongs
-- in clients/contacts.

ALTER TABLE users
    DROP COLUMN IF EXISTS project_id;

DROP INDEX IF EXISTS idx_users_project_id;
