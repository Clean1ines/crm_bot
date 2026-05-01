BEGIN;

DROP INDEX IF EXISTS idx_knowledge_base_embedding_ivfflat;

DELETE FROM knowledge_base;

UPDATE knowledge_documents
SET status = 'error',
    error = 'Knowledge reindex required after embedding dimension migration',
    updated_at = NOW()
WHERE status = 'processed';

ALTER TABLE knowledge_base
    ALTER COLUMN embedding TYPE vector(512);

CREATE INDEX IF NOT EXISTS idx_knowledge_base_embedding_ivfflat
    ON knowledge_base USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

ANALYZE knowledge_base;
ANALYZE knowledge_documents;

COMMIT;
