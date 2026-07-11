BEGIN;

ALTER TABLE knowledge_workbench_rag_eval_runs
    ADD COLUMN IF NOT EXISTS adjudication_total INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS adjudication_waiting INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS adjudication_running INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS adjudication_completed INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS adjudication_failed INTEGER NOT NULL DEFAULT 0,
    ADD COLUMN IF NOT EXISTS promotion_candidate_count INTEGER NOT NULL DEFAULT 0;

ALTER TABLE knowledge_workbench_rag_eval_runs
    ADD CONSTRAINT chk_kwb_rag_eval_adjudication_progress_non_negative
        CHECK (
            adjudication_total >= 0
            AND adjudication_waiting >= 0
            AND adjudication_running >= 0
            AND adjudication_completed >= 0
            AND adjudication_failed >= 0
            AND promotion_candidate_count >= 0
        );

ALTER TABLE knowledge_workbench_rag_eval_promoted_questions
    ADD COLUMN IF NOT EXISTS outcome_id TEXT NULL,
    ADD COLUMN IF NOT EXISTS adjudication_id TEXT NULL,
    ADD COLUMN IF NOT EXISTS reason TEXT NULL,
    ADD COLUMN IF NOT EXISTS expected_rank INTEGER NULL,
    ADD COLUMN IF NOT EXISTS expected_score DOUBLE PRECISION NULL,
    ADD COLUMN IF NOT EXISTS competitor_runtime_entry_id TEXT NULL,
    ADD COLUMN IF NOT EXISTS competitor_fact_id TEXT NULL,
    ADD COLUMN IF NOT EXISTS competitor_score DOUBLE PRECISION NULL,
    ADD COLUMN IF NOT EXISTS score_margin DOUBLE PRECISION NULL;

ALTER TABLE knowledge_workbench_rag_eval_promoted_questions
    ADD CONSTRAINT chk_kwb_rag_eval_promotion_expected_rank_positive
        CHECK (expected_rank IS NULL OR expected_rank > 0),
    ADD CONSTRAINT chk_kwb_rag_eval_promotion_reason_non_empty
        CHECK (reason IS NULL OR length(trim(reason)) > 0);

CREATE UNIQUE INDEX IF NOT EXISTS uq_kwb_rag_eval_promotions_adjudication
    ON knowledge_workbench_rag_eval_promoted_questions(adjudication_id)
    WHERE adjudication_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_promotions_outcome
    ON knowledge_workbench_rag_eval_promoted_questions(outcome_id)
    WHERE outcome_id IS NOT NULL;

COMMIT;
