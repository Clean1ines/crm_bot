-- Добавляем колонку для токена менеджерского бота в projects
ALTER TABLE projects ADD COLUMN IF NOT EXISTS manager_bot_token TEXT;

-- Создаём таблицу для хранения нескольких менеджеров проекта
CREATE TABLE IF NOT EXISTS project_managers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    manager_chat_id TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(project_id, manager_chat_id)
);

-- Индекс для быстрого поиска по project_id
CREATE INDEX IF NOT EXISTS idx_project_managers_project ON project_managers(project_id);
