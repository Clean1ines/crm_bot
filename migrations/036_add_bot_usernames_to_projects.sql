-- Add columns to store bot usernames for display in web UI
ALTER TABLE projects
ADD COLUMN client_bot_username VARCHAR(255) NULL,
ADD COLUMN manager_bot_username VARCHAR(255) NULL;

-- Index on usernames (optional, not critical)
CREATE INDEX idx_projects_client_bot_username ON projects(client_bot_username);
CREATE INDEX idx_projects_manager_bot_username ON projects(manager_bot_username);

COMMENT ON COLUMN projects.client_bot_username IS 'Username of the client bot (from Telegram)';
COMMENT ON COLUMN projects.manager_bot_username IS 'Username of the manager bot (from Telegram)';
