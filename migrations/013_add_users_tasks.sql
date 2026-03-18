-- 013_add_users_tasks.sql
-- Добавляет таблицы users (CRM), tasks (тикеты) и расширяет messages метаданными.
-- Применяется после миграций 001-012.

BEGIN;

-- -------------------------------------------------------------------------
-- 1. Таблица users: хранит расширенный профиль клиента (CRM-данные)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid REFERENCES projects(id) ON DELETE CASCADE,
    telegram_id bigint UNIQUE,
    username text,
    full_name text,
    email text,
    company text,
    phone text,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_users_project_id ON users(project_id);
CREATE INDEX IF NOT EXISTS idx_users_telegram_id ON users(telegram_id);

-- -------------------------------------------------------------------------
-- 2. Таблица tasks: задачи для менеджеров (тикеты)
-- -------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tasks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id uuid REFERENCES projects(id) ON DELETE CASCADE,
    thread_id uuid REFERENCES threads(id) ON DELETE SET NULL,
    client_id uuid REFERENCES clients(id) ON DELETE SET NULL,
    title text NOT NULL,
    description text,
    priority text DEFAULT 'normal',
    status text DEFAULT 'open', -- open, in_progress, resolved, closed
    assigned_to bigint,          -- Telegram chat_id менеджера, взявшего задачу
    created_by bigint,            -- кто создал (бот или менеджер)
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

-- Индексы для фильтрации задач
CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
CREATE INDEX IF NOT EXISTS idx_tasks_assigned_to ON tasks(assigned_to);
CREATE INDEX IF NOT EXISTS idx_tasks_project_id ON tasks(project_id);

-- -------------------------------------------------------------------------
-- 3. Расширение таблицы messages
-- -------------------------------------------------------------------------
ALTER TABLE messages 
    ADD COLUMN IF NOT EXISTS metadata jsonb DEFAULT '{}'::jsonb,
    ADD COLUMN IF NOT EXISTS immutable boolean DEFAULT true,
    ADD COLUMN IF NOT EXISTS source text DEFAULT 'telegram';

-- Индекс на thread_id уже существует, но для надёжности повторим
CREATE INDEX IF NOT EXISTS idx_messages_thread_id ON messages(thread_id);

COMMIT;
