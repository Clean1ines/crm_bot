BEGIN;

CREATE TABLE IF NOT EXISTS knowledge_workbench_rag_eval_question_adjudications (
    adjudication_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES knowledge_workbench_rag_eval_runs(run_id) ON DELETE CASCADE,
    project_id UUID NOT NULL,
    question_id TEXT NOT NULL REFERENCES knowledge_workbench_rag_eval_questions(question_id) ON DELETE CASCADE,
    outcome_id TEXT NOT NULL REFERENCES knowledge_workbench_rag_eval_retrieval_outcomes(outcome_id) ON DELETE CASCADE,
    expected_runtime_entry_id TEXT NOT NULL,
    expected_fact_id TEXT NOT NULL,
    verdict TEXT NOT NULL,
    promotion_recommended BOOLEAN NOT NULL,
    reason TEXT NOT NULL,
    contract_version TEXT NOT NULL,
    model_ref TEXT NOT NULL,
    account_ref TEXT NOT NULL,
    slot_index INTEGER NOT NULL,
    attempt_id TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,

    CONSTRAINT chk_kwb_rag_eval_adjudication_verdict
        CHECK (
            verdict IN (
                'valid_target_query',
                'ambiguous',
                'wrong_expected_target',
                'unsupported_by_claim',
                'duplicate_query',
                'overlapping_published_entries'
            )
        ),
    CONSTRAINT chk_kwb_rag_eval_adjudication_recommendation_gate
        CHECK (
            promotion_recommended = FALSE
            OR verdict = 'valid_target_query'
        ),
    CONSTRAINT chk_kwb_rag_eval_adjudication_contract
        CHECK (contract_version = 'workbench_rag_eval_adjudication.v1'),
    CONSTRAINT chk_kwb_rag_eval_adjudication_reason_non_empty
        CHECK (length(trim(reason)) > 0),
    CONSTRAINT chk_kwb_rag_eval_adjudication_slot_non_negative
        CHECK (slot_index >= 0),
    CONSTRAINT uq_kwb_rag_eval_adjudication_logical
        UNIQUE (run_id, question_id, outcome_id)
);

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_adjudications_run
    ON knowledge_workbench_rag_eval_question_adjudications(run_id);

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_adjudications_project_verdict
    ON knowledge_workbench_rag_eval_question_adjudications(project_id, verdict);

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_adjudications_attempt
    ON knowledge_workbench_rag_eval_question_adjudications(attempt_id);

COMMIT;
