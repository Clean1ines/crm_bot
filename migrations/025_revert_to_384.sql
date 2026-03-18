BEGIN;
ALTER TABLE knowledge_base DROP COLUMN IF EXISTS embedding_1024;
ALTER TABLE knowledge_base ALTER COLUMN embedding TYPE vector(384);
COMMIT;
