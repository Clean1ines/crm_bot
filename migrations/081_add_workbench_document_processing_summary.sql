BEGIN;

ALTER TABLE knowledge_workbench_documents
    ADD COLUMN IF NOT EXISTS processing_summary JSONB NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_kwb_documents_processing_summary_gin
    ON knowledge_workbench_documents
    USING gin (processing_summary);

COMMIT;
