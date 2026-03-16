-- Добавляем поле manager_chat_id в таблицу threads для связи с менеджером,
-- который отвечает на эскалированный диалог.
ALTER TABLE threads ADD COLUMN manager_chat_id TEXT;

-- Индекс для быстрого поиска активных тредов, ожидающих ответа менеджера.
CREATE INDEX idx_threads_manager_chat ON threads(manager_chat_id) WHERE status = 'manual';
