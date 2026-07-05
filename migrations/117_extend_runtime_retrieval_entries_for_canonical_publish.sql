-- Additive support for using runtime retrieval entries as the canonical
-- published fact object. Canonical facts/registries remain in place for the
-- transition; publication and search paths are intentionally unchanged here.

ALTER TABLE IF EXISTS knowledge_workbench_runtime_retrieval_entries
    ADD COLUMN IF NOT EXISTS publication_id TEXT NULL,
    ADD COLUMN IF NOT EXISTS workflow_run_id TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS source_document_ref TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS curation_item_ref TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS claim_kind TEXT NOT NULL DEFAULT 'faq_workbench_fact',
    ADD COLUMN IF NOT EXISTS granularity TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS exclusion_scope TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS evidence_block TEXT NOT NULL DEFAULT '',
    ADD COLUMN IF NOT EXISTS triples JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS source_claim_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ NULL;

ALTER TABLE IF EXISTS knowledge_workbench_runtime_retrieval_entries
    ALTER COLUMN fact_id DROP NOT NULL;

ALTER TABLE IF EXISTS knowledge_workbench_runtime_retrieval_entries
    DROP CONSTRAINT IF EXISTS knowledge_workbench_runtime_retrieval_entries_fact_id_fkey;
