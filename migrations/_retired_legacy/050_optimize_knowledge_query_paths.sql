BEGIN;

CREATE INDEX IF NOT EXISTS idx_knowledge_documents_project_status_id
    ON knowledge_documents(project_id, status, id);

CREATE INDEX IF NOT EXISTS idx_knowledge_documents_project_created_at
    ON knowledge_documents(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_knowledge_base_project_document
    ON knowledge_base(project_id, document_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_base_embedding_ivfflat
    ON knowledge_base USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

ANALYZE knowledge_documents;
ANALYZE knowledge_base;

COMMIT;
