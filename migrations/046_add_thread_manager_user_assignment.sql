-- Migration 046: Add canonical platform-user assignment for manual threads.
--
-- manager_chat_id is a Telegram transport identifier and remains as a legacy
-- bridge while manager bot reply sessions still need chat ids. The domain
-- assignment is manager_user_id.

ALTER TABLE threads
    ADD COLUMN IF NOT EXISTS manager_user_id uuid REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_threads_manager_user
    ON threads(manager_user_id)
    WHERE status = 'manual';

UPDATE threads t
SET manager_user_id = u.id
FROM users u
WHERE t.manager_user_id IS NULL
  AND t.manager_chat_id IS NOT NULL
  AND CAST(u.telegram_id AS TEXT) = CAST(t.manager_chat_id AS TEXT);
