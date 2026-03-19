-- 027_add_user_memory.sql
-- Таблица для долговременной памяти пользователя (предпочтения, факты, история проблем)

BEGIN;

CREATE TABLE IF NOT EXISTS user_memory (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid REFERENCES projects(id) ON DELETE CASCADE,
    client_id uuid REFERENCES clients(id) ON DELETE CASCADE,
    key text NOT NULL,
    value jsonb NOT NULL,
    type text NOT NULL,  -- например: 'preference', 'fact', 'issue'
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_user_memory_project_client ON user_memory(project_id, client_id);
CREATE INDEX IF NOT EXISTS idx_user_memory_type ON user_memory(type);

COMMIT;
