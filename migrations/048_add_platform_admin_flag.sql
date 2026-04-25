-- Migration 048: Add global platform admin flag to platform users.
--
-- Project roles stay in project_members. This flag is only for platform-level
-- ownership/operations.

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS is_platform_admin boolean NOT NULL DEFAULT false;

CREATE INDEX IF NOT EXISTS idx_users_platform_admin
    ON users(is_platform_admin)
    WHERE is_platform_admin = true;
