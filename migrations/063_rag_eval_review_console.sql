-- Migration 063: RAG Eval Review Console persistence.
--
-- Eval remains diagnostic only: generated questions become review candidates and
-- are applied to production knowledge enrichment only after an explicit human
-- review action.

BEGIN;

CREATE TABLE IF NOT EXISTS rag_eval_question_reviews (
    id TEXT PRIMARY KEY,
    question_id TEXT NOT NULL REFERENCES rag_eval_questions(id) ON DELETE CASCADE,
    run_id TEXT NOT NULL REFERENCES rag_eval_runs(id) ON DELETE CASCADE,
    dataset_id TEXT NOT NULL REFERENCES rag_eval_datasets(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    source_chunk_id TEXT,
    status TEXT NOT NULL DEFAULT 'candidate',
    original_question TEXT NOT NULL,
    edited_question TEXT,
    review_reason TEXT NOT NULL DEFAULT '',
    reviewed_by TEXT,
    reviewed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_rag_eval_question_reviews_question UNIQUE (question_id),
    CONSTRAINT ck_rag_eval_question_reviews_status CHECK (
        status IN ('candidate', 'accepted', 'rejected', 'edited', 'applied')
    ),
    CONSTRAINT ck_rag_eval_question_reviews_original_not_blank CHECK (btrim(original_question) <> ''),
    CONSTRAINT ck_rag_eval_question_reviews_edited_not_blank CHECK (
        edited_question IS NULL OR btrim(edited_question) <> ''
    )
);

CREATE INDEX IF NOT EXISTS idx_rag_eval_question_reviews_run_status
    ON rag_eval_question_reviews(run_id, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_rag_eval_question_reviews_document
    ON rag_eval_question_reviews(project_id, document_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS rag_eval_report_snapshots (
    id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES rag_eval_runs(id) ON DELETE CASCADE,
    dataset_id TEXT NOT NULL REFERENCES rag_eval_datasets(id) ON DELETE CASCADE,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    score DOUBLE PRECISION NOT NULL DEFAULT 0,
    readiness TEXT NOT NULL DEFAULT 'needs_review',
    summary_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    problem_map_json JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_rag_eval_report_snapshots_summary_object CHECK (jsonb_typeof(summary_json) = 'object'),
    CONSTRAINT ck_rag_eval_report_snapshots_problem_map_object CHECK (jsonb_typeof(problem_map_json) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_rag_eval_report_snapshots_document_created
    ON rag_eval_report_snapshots(project_id, document_id, created_at DESC);

COMMENT ON TABLE rag_eval_question_reviews IS
    'Human review lifecycle for generated RAG eval questions before production enrichment changes are applied.';

COMMENT ON TABLE rag_eval_report_snapshots IS
    'Optional structured RAG eval review snapshots for product UI/report history.';

COMMIT;
