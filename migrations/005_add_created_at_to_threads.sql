-- Добавляем поле created_at в таблицу threads (если его нет)
ALTER TABLE threads ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW();