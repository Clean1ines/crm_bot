-- Migration 064: live RAG eval review group projection.
--
-- Stores fragment-scoped Review Console cards while a retrieval eval run is
-- still running. Eval remains diagnostic: no production enrichment is changed
-- by this projection.

BEGIN;

CREATE TABLE IF NOT EXISTS rag_eval_review_groups (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES rag_eval_runs(id) ON DELETE CASCADE,
    dataset_id TEXT NOT NULL REFERENCES rag_eval_datasets(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    source_chunk_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    questions_total INTEGER NOT NULL DEFAULT 0,
    checked_questions INTEGER NOT NULL DEFAULT 0,
    reliable_count INTEGER NOT NULL DEFAULT 0,
    weak_count INTEGER NOT NULL DEFAULT 0,
    confused_count INTEGER NOT NULL DEFAULT 0,
    missing_count INTEGER NOT NULL DEFAULT 0,
    improvement_count INTEGER NOT NULL DEFAULT 0,
    review_payload_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    error TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_rag_eval_review_groups_run_source UNIQUE (run_id, source_chunk_id),
    CONSTRAINT ck_rag_eval_review_groups_status CHECK (
        status IN (
            'queued',
            'generating_questions',
            'checking_retrieval',
            'ready_for_review',
            'failed'
        )
    ),
    CONSTRAINT ck_rag_eval_review_groups_counts_non_negative CHECK (
        questions_total >= 0
        AND checked_questions >= 0
        AND reliable_count >= 0
        AND weak_count >= 0
        AND confused_count >= 0
        AND missing_count >= 0
        AND improvement_count >= 0
    ),
    CONSTRAINT ck_rag_eval_review_groups_payload_object CHECK (
        jsonb_typeof(review_payload_json) = 'object'
    )
);

CREATE INDEX IF NOT EXISTS idx_rag_eval_review_groups_run_status
    ON rag_eval_review_groups(run_id, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_rag_eval_review_groups_document
    ON rag_eval_review_groups(project_id, document_id, updated_at DESC);

COMMENT ON TABLE rag_eval_review_groups IS
    'Fragment-scoped RAG eval Review Console projection updated during streaming retrieval eval runs.';

COMMIT;
