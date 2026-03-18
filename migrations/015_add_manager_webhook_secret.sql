-- 015_add_manager_webhook_secret.sql
-- Добавляет колонку manager_webhook_secret в таблицу projects для хранения секрета вебхука менеджерского бота.

BEGIN;

ALTER TABLE projects ADD COLUMN IF NOT EXISTS manager_webhook_secret text;

COMMENT ON COLUMN projects.manager_webhook_secret IS 'Секретный токен для верификации запросов к /manager/webhook';

COMMIT;
