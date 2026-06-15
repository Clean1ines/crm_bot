-- Workbench RAG Eval over published compacted-claim runtime retrieval.
-- This contour intentionally evaluates retrieval only and does not store answer_text.

CREATE TABLE IF NOT EXISTS knowledge_workbench_rag_eval_runs (
    run_id TEXT PRIMARY KEY,
    project_id UUID NOT NULL,
    publication_id TEXT NULL,
    source_document_ref TEXT NULL,
    status TEXT NOT NULL,
    question_generation_model TEXT NULL,
    question_generation_prompt_version TEXT NOT NULL,
    total_entries INTEGER NOT NULL DEFAULT 0,
    total_questions INTEGER NOT NULL DEFAULT 0,
    completed_questions INTEGER NOT NULL DEFAULT 0,
    top1_hits INTEGER NOT NULL DEFAULT 0,
    top3_hits INTEGER NOT NULL DEFAULT 0,
    top5_hits INTEGER NOT NULL DEFAULT 0,
    misses INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMPTZ NOT NULL,
    started_at TIMESTAMPTZ NULL,
    completed_at TIMESTAMPTZ NULL,
    error_message TEXT NULL,

    CONSTRAINT chk_kwb_rag_eval_run_status
        CHECK (status IN ('created', 'running', 'completed', 'failed')),
    CONSTRAINT chk_kwb_rag_eval_run_prompt_version_non_empty
        CHECK (length(trim(question_generation_prompt_version)) > 0),
    CONSTRAINT chk_kwb_rag_eval_run_counts_non_negative
        CHECK (
            total_entries >= 0
            AND total_questions >= 0
            AND completed_questions >= 0
            AND top1_hits >= 0
            AND top3_hits >= 0
            AND top5_hits >= 0
            AND misses >= 0
        )
);

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_runs_project_created
    ON knowledge_workbench_rag_eval_runs(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_runs_publication
    ON knowledge_workbench_rag_eval_runs(publication_id);

CREATE TABLE IF NOT EXISTS knowledge_workbench_rag_eval_questions (
    question_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES knowledge_workbench_rag_eval_runs(run_id) ON DELETE CASCADE,
    project_id UUID NOT NULL,
    expected_runtime_entry_id TEXT NOT NULL,
    expected_fact_id TEXT NOT NULL,
    question TEXT NOT NULL,
    question_kind TEXT NOT NULL,
    source TEXT NOT NULL,
    generation_model TEXT NULL,
    prompt_version TEXT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,

    CONSTRAINT chk_kwb_rag_eval_question_kind
        CHECK (
            question_kind IN (
                'paraphrase',
                'synonym',
                'naive_user_question',
                'domain_specific',
                'existing_possible_question'
            )
        ),
    CONSTRAINT chk_kwb_rag_eval_question_status
        CHECK (status IN ('created', 'evaluated', 'failed')),
    CONSTRAINT chk_kwb_rag_eval_question_text_non_empty
        CHECK (length(trim(question)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_questions_run
    ON knowledge_workbench_rag_eval_questions(run_id);

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_questions_expected_entry
    ON knowledge_workbench_rag_eval_questions(expected_runtime_entry_id);

CREATE TABLE IF NOT EXISTS knowledge_workbench_rag_eval_retrieval_results (
    result_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES knowledge_workbench_rag_eval_runs(run_id) ON DELETE CASCADE,
    question_id TEXT NOT NULL REFERENCES knowledge_workbench_rag_eval_questions(question_id) ON DELETE CASCADE,
    project_id UUID NOT NULL,
    expected_runtime_entry_id TEXT NOT NULL,
    matched_runtime_entry_id TEXT NOT NULL,
    matched_fact_id TEXT NOT NULL,
    rank INTEGER NOT NULL,
    score DOUBLE PRECISION NOT NULL,
    top1_hit BOOLEAN NOT NULL,
    top3_hit BOOLEAN NOT NULL,
    top5_hit BOOLEAN NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,

    CONSTRAINT chk_kwb_rag_eval_result_rank_positive
        CHECK (rank > 0)
);

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_results_question
    ON knowledge_workbench_rag_eval_retrieval_results(question_id);

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_results_run
    ON knowledge_workbench_rag_eval_retrieval_results(run_id);

CREATE TABLE IF NOT EXISTS knowledge_workbench_rag_eval_promoted_questions (
    promotion_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES knowledge_workbench_rag_eval_runs(run_id) ON DELETE CASCADE,
    question_id TEXT NOT NULL REFERENCES knowledge_workbench_rag_eval_questions(question_id) ON DELETE CASCADE,
    project_id UUID NOT NULL,
    target_runtime_entry_id TEXT NOT NULL,
    target_fact_id TEXT NOT NULL,
    question TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    applied_at TIMESTAMPTZ NULL,

    CONSTRAINT chk_kwb_rag_eval_promotion_status
        CHECK (status IN ('candidate', 'accepted', 'rejected', 'applied')),
    CONSTRAINT chk_kwb_rag_eval_promotion_question_non_empty
        CHECK (length(trim(question)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_promotions_run
    ON knowledge_workbench_rag_eval_promoted_questions(run_id);

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_promotions_target
    ON knowledge_workbench_rag_eval_promoted_questions(target_runtime_entry_id);
