-- Migration 043: Link project-scoped clients/contacts to platform users.
--
-- `users` are platform identities. `clients` are project-scoped CRM contacts.
-- A physical person may be both, so clients.user_id is an optional bridge to
-- the platform identity without turning clients into auth users.

ALTER TABLE clients
    ADD COLUMN IF NOT EXISTS user_id uuid REFERENCES users(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_clients_user_id ON clients(user_id);

UPDATE clients c
SET user_id = u.id
FROM users u
WHERE c.user_id IS NULL
  AND u.telegram_id IS NOT NULL
  AND CAST(c.chat_id AS TEXT) = CAST(u.telegram_id AS TEXT);
