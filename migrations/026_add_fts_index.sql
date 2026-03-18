BEGIN;
-- Добавляем колонку для tsvector
ALTER TABLE knowledge_base ADD COLUMN IF NOT EXISTS tsv tsvector;
-- Обновляем tsvector для существующих записей
UPDATE knowledge_base SET tsv = to_tsvector('russian', content);
-- Создаем индекс для полнотекстового поиска
CREATE INDEX IF NOT EXISTS idx_knowledge_tsv ON knowledge_base USING gin(tsv);
-- Триггер для автоматического обновления tsvector при изменении
CREATE OR REPLACE FUNCTION knowledge_base_tsv_update() RETURNS trigger AS $$
BEGIN
  NEW.tsv = to_tsvector('russian', NEW.content);
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS knowledge_base_tsv_trigger ON knowledge_base;
CREATE TRIGGER knowledge_base_tsv_trigger
  BEFORE INSERT OR UPDATE OF content
  ON knowledge_base
  FOR EACH ROW
  EXECUTE FUNCTION knowledge_base_tsv_update();
COMMIT;
