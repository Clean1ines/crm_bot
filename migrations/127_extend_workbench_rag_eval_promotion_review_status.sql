ALTER TABLE knowledge_workbench_rag_eval_promoted_questions
    ADD COLUMN IF NOT EXISTS reviewed_at TIMESTAMPTZ NULL,
    ADD COLUMN IF NOT EXISTS review_reason TEXT NULL;

ALTER TABLE knowledge_workbench_rag_eval_promoted_questions
    DROP CONSTRAINT IF EXISTS chk_kwb_rag_eval_promotion_status;

UPDATE knowledge_workbench_rag_eval_promoted_questions
SET status = 'approved'
WHERE status = 'accepted';

ALTER TABLE knowledge_workbench_rag_eval_promoted_questions
    ADD CONSTRAINT chk_kwb_rag_eval_promotion_status
    CHECK (
        status IN (
            'candidate',
            'approved',
            'rejected',
            'applying',
            'applied',
            'superseded',
            'regression_failed',
            'rolled_back'
        )
    );

ALTER TABLE knowledge_workbench_rag_eval_promoted_questions
    DROP CONSTRAINT IF EXISTS chk_kwb_rag_eval_promotion_review_reason;

ALTER TABLE knowledge_workbench_rag_eval_promoted_questions
    ADD CONSTRAINT chk_kwb_rag_eval_promotion_review_reason
    CHECK (
        status <> 'rejected'
        OR (
            review_reason IS NOT NULL
            AND length(trim(review_reason)) > 0
        )
    );

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_promotions_run_project_status
    ON knowledge_workbench_rag_eval_promoted_questions (
        run_id,
        project_id,
        status
    );
