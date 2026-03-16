-- Добавляем поле context_summary в таблицу threads для хранения краткого содержания диалога
ALTER TABLE threads ADD COLUMN IF NOT EXISTS context_summary TEXT;
