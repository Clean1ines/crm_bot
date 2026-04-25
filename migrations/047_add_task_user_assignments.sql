-- Migration 047: Add canonical platform-user references to tasks.
--
-- assigned_to and created_by are legacy Telegram transport ids from the
-- original manager-bot-only model. New task/ticket logic should use
-- assigned_user_id and created_by_user_id.

ALTER TABLE tasks
    ADD COLUMN IF NOT EXISTS assigned_user_id uuid REFERENCES users(id) ON DELETE SET NULL,
    ADD COLUMN IF NOT EXISTS created_by_user_id uuid REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_tasks_assigned_user_id ON tasks(assigned_user_id);
CREATE INDEX IF NOT EXISTS idx_tasks_created_by_user_id ON tasks(created_by_user_id);

UPDATE tasks t
SET assigned_user_id = u.id
FROM users u
WHERE t.assigned_user_id IS NULL
  AND t.assigned_to IS NOT NULL
  AND CAST(u.telegram_id AS TEXT) = CAST(t.assigned_to AS TEXT);

UPDATE tasks t
SET created_by_user_id = u.id
FROM users u
WHERE t.created_by_user_id IS NULL
  AND t.created_by IS NOT NULL
  AND CAST(u.telegram_id AS TEXT) = CAST(t.created_by AS TEXT);
