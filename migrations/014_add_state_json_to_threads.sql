-- 014_add_state_json_to_threads.sql
-- Добавляет колонку state_json типа JSONB в таблицу threads для хранения состояния графа.
-- Применяется после миграций 001-013.

BEGIN;

ALTER TABLE threads ADD COLUMN IF NOT EXISTS state_json jsonb;

COMMENT ON COLUMN threads.state_json IS 'Сериализованное состояние LangGraph для восстановления диалога';

COMMIT;
