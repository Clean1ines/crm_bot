BEGIN;

ALTER TABLE knowledge_workbench_rag_eval_questions
    ADD COLUMN IF NOT EXISTS evaluation_role TEXT;

UPDATE knowledge_workbench_rag_eval_questions
SET evaluation_role = CASE
    WHEN source = 'published_possible_question'
        THEN 'baseline'
    ELSE 'promotion_pool'
END
WHERE evaluation_role IS NULL;

ALTER TABLE knowledge_workbench_rag_eval_questions
    ALTER COLUMN evaluation_role SET NOT NULL;

ALTER TABLE knowledge_workbench_rag_eval_questions
    DROP CONSTRAINT IF EXISTS
        knowledge_workbench_rag_eval_questions_evaluation_role_check;

ALTER TABLE knowledge_workbench_rag_eval_questions
    ADD CONSTRAINT
        knowledge_workbench_rag_eval_questions_evaluation_role_check
    CHECK (
        evaluation_role IN (
            'baseline',
            'promotion_pool',
            'holdout'
        )
    );

ALTER TABLE knowledge_workbench_rag_eval_questions
    DROP CONSTRAINT IF EXISTS holdout_not_promotion_eligible;

ALTER TABLE knowledge_workbench_rag_eval_questions
    DROP CONSTRAINT IF EXISTS baseline_not_promotion_eligible;

ALTER TABLE knowledge_workbench_rag_eval_questions
    ADD CONSTRAINT holdout_not_promotion_eligible
    CHECK (
        evaluation_role <> 'holdout'
        OR promotion_eligible = FALSE
    );

ALTER TABLE knowledge_workbench_rag_eval_questions
    ADD CONSTRAINT baseline_not_promotion_eligible
    CHECK (
        evaluation_role <> 'baseline'
        OR promotion_eligible = FALSE
    );

CREATE INDEX IF NOT EXISTS
    idx_workbench_rag_eval_questions_run_role
ON knowledge_workbench_rag_eval_questions (
    run_id,
    evaluation_role
);

COMMIT;
