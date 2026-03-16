-- Таблица для очереди фоновых задач (уведомления менеджерам, вебхуки и т.д.)
CREATE TABLE IF NOT EXISTS execution_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    task_type TEXT NOT NULL,
    payload JSONB,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- Индекс для быстрой выборки задач по статусу
CREATE INDEX IF NOT EXISTS idx_queue_status ON execution_queue(status, created_at);
