BEGIN;

CREATE TABLE IF NOT EXISTS
    knowledge_workbench_rag_eval_retrieval_outcomes (
        outcome_id TEXT PRIMARY KEY,
        run_id TEXT NOT NULL,
        question_id TEXT NOT NULL,
        project_id UUID NOT NULL,
        evaluation_stage TEXT NOT NULL,

        expected_runtime_entry_id TEXT NOT NULL,
        expected_fact_id TEXT NOT NULL,

        expected_rank INTEGER,
        expected_score DOUBLE PRECISION,

        best_competitor_runtime_entry_id TEXT,
        best_competitor_fact_id TEXT,
        best_competitor_score DOUBLE PRECISION,

        score_margin DOUBLE PRECISION,
        classification TEXT NOT NULL,
        created_at TIMESTAMPTZ NOT NULL,

        CONSTRAINT
            workbench_rag_eval_retrieval_outcomes_expected_rank_check
        CHECK (
            expected_rank IS NULL
            OR expected_rank > 0
        ),

        CONSTRAINT
            workbench_rag_eval_retrieval_outcomes_stage_check
        CHECK (
            evaluation_stage IN (
                'initial',
                'verification_before',
                'verification_after'
            )
        ),

        CONSTRAINT
            workbench_rag_eval_retrieval_outcomes_classification_check
        CHECK (
            classification IN (
                'pass_strong',
                'pass_weak',
                'confusion',
                'miss',
                'existing_alias_retrieval_failure'
            )
        ),

        CONSTRAINT
            workbench_rag_eval_retrieval_outcomes_run_question_stage_key
        UNIQUE (
            run_id,
            question_id,
            evaluation_stage
        )
    );

CREATE INDEX IF NOT EXISTS
    idx_workbench_rag_eval_outcomes_run
ON knowledge_workbench_rag_eval_retrieval_outcomes (
    run_id
);

CREATE INDEX IF NOT EXISTS
    idx_workbench_rag_eval_outcomes_question
ON knowledge_workbench_rag_eval_retrieval_outcomes (
    question_id
);

CREATE INDEX IF NOT EXISTS
    idx_workbench_rag_eval_outcomes_project_classification
ON knowledge_workbench_rag_eval_retrieval_outcomes (
    project_id,
    classification
);

CREATE INDEX IF NOT EXISTS
    idx_workbench_rag_eval_outcomes_expected_entry
ON knowledge_workbench_rag_eval_retrieval_outcomes (
    expected_runtime_entry_id
);

COMMIT;
