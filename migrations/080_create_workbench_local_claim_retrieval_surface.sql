BEGIN;

-- Phase 15.1
-- Persist embedding-backed local claim retrieval surface before Prompt C.
--
-- This table is a processing-run scoped temporary/observability retrieval
-- projection for Prompt A claim observations. It is not the customer runtime
-- retrieval surface. It exists to make Prompt C clustering use semantic
-- candidate retrieval instead of only lexical/ngram/triple overlap.

CREATE TABLE IF NOT EXISTS knowledge_workbench_local_claim_retrieval_entries (
    entry_id TEXT PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id TEXT NOT NULL REFERENCES knowledge_workbench_documents(document_id) ON DELETE CASCADE,
    processing_run_id TEXT NOT NULL REFERENCES knowledge_workbench_processing_runs(processing_run_id) ON DELETE CASCADE,
    section_id TEXT NOT NULL REFERENCES knowledge_workbench_document_sections(section_id) ON DELETE CASCADE,
    node_run_id TEXT NOT NULL,
    search_document_id TEXT NOT NULL,
    local_ref TEXT NOT NULL,
    claim TEXT NOT NULL,
    claim_kind TEXT NOT NULL DEFAULT '',
    granularity TEXT NOT NULL DEFAULT '',
    search_text TEXT NOT NULL,
    triples_payload JSONB NOT NULL DEFAULT '[]'::jsonb,
    possible_questions_payload JSONB NOT NULL DEFAULT '[]'::jsonb,
    scope TEXT NOT NULL DEFAULT '',
    exclusion_scope TEXT NOT NULL DEFAULT '',
    evidence_block TEXT NOT NULL DEFAULT '',
    relation_texts_payload JSONB NOT NULL DEFAULT '[]'::jsonb,
    embedding vector(384) NOT NULL,
    embedding_text_version TEXT NOT NULL DEFAULT 'workbench_local_claim_retrieval_v1',
    status TEXT NOT NULL DEFAULT 'indexed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_kwb_local_claim_retrieval_search_document
        UNIQUE (project_id, document_id, processing_run_id, search_document_id),
    CONSTRAINT ck_kwb_local_claim_retrieval_status
        CHECK (status IN ('indexed', 'superseded', 'deleted')),
    CONSTRAINT ck_kwb_local_claim_retrieval_claim_not_blank
        CHECK (btrim(claim) <> ''),
    CONSTRAINT ck_kwb_local_claim_retrieval_search_text_not_blank
        CHECK (btrim(search_text) <> '')
);

CREATE INDEX IF NOT EXISTS idx_kwb_local_claim_retrieval_run
    ON knowledge_workbench_local_claim_retrieval_entries (
        project_id,
        document_id,
        processing_run_id,
        status
    );

CREATE INDEX IF NOT EXISTS idx_kwb_local_claim_retrieval_node_run
    ON knowledge_workbench_local_claim_retrieval_entries (
        project_id,
        document_id,
        processing_run_id,
        node_run_id
    );

CREATE INDEX IF NOT EXISTS idx_kwb_local_claim_retrieval_embedding_ivfflat
    ON knowledge_workbench_local_claim_retrieval_entries
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_kwb_local_claim_retrieval_search_text_fts
    ON knowledge_workbench_local_claim_retrieval_entries
    USING gin (to_tsvector('russian', search_text));

ANALYZE knowledge_workbench_local_claim_retrieval_entries;

COMMIT;
