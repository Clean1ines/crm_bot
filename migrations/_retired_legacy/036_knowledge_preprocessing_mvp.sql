BEGIN;

ALTER TABLE knowledge_documents
    ADD COLUMN IF NOT EXISTS preprocessing_mode TEXT NOT NULL DEFAULT 'plain',
    ADD COLUMN IF NOT EXISTS preprocessing_status TEXT NOT NULL DEFAULT 'not_requested',
    ADD COLUMN IF NOT EXISTS preprocessing_error TEXT,
    ADD COLUMN IF NOT EXISTS preprocessing_model TEXT,
    ADD COLUMN IF NOT EXISTS preprocessing_prompt_version TEXT,
    ADD COLUMN IF NOT EXISTS preprocessing_metrics JSONB NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE knowledge_base
    ADD COLUMN IF NOT EXISTS entry_type TEXT NOT NULL DEFAULT 'chunk',
    ADD COLUMN IF NOT EXISTS title TEXT,
    ADD COLUMN IF NOT EXISTS source_excerpt TEXT,
    ADD COLUMN IF NOT EXISTS questions JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS synonyms JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS tags JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS embedding_text TEXT;

CREATE INDEX IF NOT EXISTS idx_knowledge_documents_project_preprocessing_mode
    ON knowledge_documents(project_id, preprocessing_mode);

CREATE INDEX IF NOT EXISTS idx_knowledge_base_document_entry_type
    ON knowledge_base(document_id, entry_type);

COMMIT;
