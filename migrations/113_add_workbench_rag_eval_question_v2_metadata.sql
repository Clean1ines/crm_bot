ALTER TABLE knowledge_workbench_rag_eval_questions
    ADD COLUMN IF NOT EXISTS contract_version TEXT,
    ADD COLUMN IF NOT EXISTS promotion_eligible BOOLEAN NOT NULL DEFAULT FALSE,
    ADD COLUMN IF NOT EXISTS ambiguity_risk TEXT,
    ADD COLUMN IF NOT EXISTS generation_rationale TEXT;

ALTER TABLE knowledge_workbench_rag_eval_questions
    DROP CONSTRAINT IF EXISTS ck_workbench_rag_eval_question_ambiguity_risk;

ALTER TABLE knowledge_workbench_rag_eval_questions
    ADD CONSTRAINT ck_workbench_rag_eval_question_ambiguity_risk
    CHECK (
        ambiguity_risk IS NULL
        OR ambiguity_risk IN ('low', 'medium', 'high')
    );

ALTER TABLE knowledge_workbench_rag_eval_questions
    DROP CONSTRAINT IF EXISTS ck_workbench_rag_eval_question_promotion_eligibility;

ALTER TABLE knowledge_workbench_rag_eval_questions
    ADD CONSTRAINT ck_workbench_rag_eval_question_promotion_eligibility
    CHECK (
        NOT promotion_eligible
        OR ambiguity_risk = 'low'
    );

CREATE INDEX IF NOT EXISTS idx_workbench_rag_eval_questions_contract
    ON knowledge_workbench_rag_eval_questions (
        contract_version,
        promotion_eligible,
        ambiguity_risk
    );
