CREATE TABLE IF NOT EXISTS knowledge_workbench_rag_eval_verifications (
    verification_id TEXT PRIMARY KEY,
    revision_id TEXT NOT NULL
        REFERENCES knowledge_workbench_rag_eval_embedding_revisions(revision_id)
        ON DELETE RESTRICT,
    project_id UUID NOT NULL
        REFERENCES projects(id)
        ON DELETE RESTRICT,
    source_rag_eval_run_id TEXT NOT NULL
        REFERENCES knowledge_workbench_rag_eval_runs(run_id)
        ON DELETE RESTRICT,
    runtime_entry_id TEXT NOT NULL
        REFERENCES knowledge_workbench_runtime_retrieval_entries(runtime_entry_id)
        ON DELETE RESTRICT,

    status TEXT NOT NULL,
    policy_version TEXT NOT NULL,
    decision TEXT NULL,
    failure_reasons JSONB NOT NULL DEFAULT '[]'::jsonb,
    metrics JSONB NULL,

    created_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NULL,
    failed_at TIMESTAMPTZ NULL,
    error_message TEXT NULL,

    CONSTRAINT uq_kwb_rag_eval_verification_revision
        UNIQUE (revision_id),
    CONSTRAINT chk_kwb_rag_eval_verification_status
        CHECK (
            status IN (
                'pending',
                'running',
                'passed',
                'regression_failed',
                'failed'
            )
        ),
    CONSTRAINT chk_kwb_rag_eval_verification_decision
        CHECK (
            decision IS NULL
            OR decision IN ('acceptable', 'regression')
        ),
    CONSTRAINT chk_kwb_rag_eval_verification_failure_reasons
        CHECK (jsonb_typeof(failure_reasons) = 'array'),
    CONSTRAINT chk_kwb_rag_eval_verification_metrics
        CHECK (
            metrics IS NULL
            OR jsonb_typeof(metrics) = 'object'
        ),
    CONSTRAINT chk_kwb_rag_eval_verification_state
        CHECK (
            (
                status IN ('pending', 'running')
                AND decision IS NULL
                AND metrics IS NULL
                AND completed_at IS NULL
                AND failed_at IS NULL
                AND error_message IS NULL
            )
            OR (
                status = 'passed'
                AND decision = 'acceptable'
                AND metrics IS NOT NULL
                AND completed_at IS NOT NULL
                AND failed_at IS NULL
                AND error_message IS NULL
            )
            OR (
                status = 'regression_failed'
                AND decision = 'regression'
                AND metrics IS NOT NULL
                AND jsonb_array_length(failure_reasons) > 0
                AND completed_at IS NOT NULL
                AND failed_at IS NULL
                AND error_message IS NULL
            )
            OR (
                status = 'failed'
                AND decision IS NULL
                AND completed_at IS NULL
                AND failed_at IS NOT NULL
                AND error_message IS NOT NULL
                AND btrim(error_message) <> ''
            )
        )
);

CREATE TABLE IF NOT EXISTS knowledge_workbench_rag_eval_verification_queries (
    verification_query_id TEXT PRIMARY KEY,
    verification_id TEXT NOT NULL
        REFERENCES knowledge_workbench_rag_eval_verifications(verification_id)
        ON DELETE CASCADE,
    revision_id TEXT NOT NULL
        REFERENCES knowledge_workbench_rag_eval_embedding_revisions(revision_id)
        ON DELETE RESTRICT,
    source_rag_eval_run_id TEXT NOT NULL
        REFERENCES knowledge_workbench_rag_eval_runs(run_id)
        ON DELETE RESTRICT,
    project_id UUID NOT NULL
        REFERENCES projects(id)
        ON DELETE RESTRICT,

    question_id TEXT NULL
        REFERENCES knowledge_workbench_rag_eval_questions(question_id)
        ON DELETE RESTRICT,
    promotion_id TEXT NULL
        REFERENCES knowledge_workbench_rag_eval_promoted_questions(promotion_id)
        ON DELETE RESTRICT,
    query_text TEXT NOT NULL,
    dataset_role TEXT NOT NULL,
    expected_runtime_entry_id TEXT NOT NULL
        REFERENCES knowledge_workbench_runtime_retrieval_entries(runtime_entry_id)
        ON DELETE RESTRICT,
    expected_fact_id TEXT NOT NULL,
    source_runtime_entry_id TEXT NOT NULL
        REFERENCES knowledge_workbench_runtime_retrieval_entries(runtime_entry_id)
        ON DELETE RESTRICT,
    source_outcome_id TEXT NULL
        REFERENCES knowledge_workbench_rag_eval_retrieval_outcomes(outcome_id)
        ON DELETE RESTRICT,
    created_at TIMESTAMPTZ NOT NULL,

    CONSTRAINT uq_kwb_rag_eval_verification_query_identity
        UNIQUE (
            verification_id,
            dataset_role,
            query_text,
            expected_runtime_entry_id
        ),
    CONSTRAINT uq_kwb_rag_eval_verification_promotion_query
        UNIQUE (verification_id, promotion_id),
    CONSTRAINT chk_kwb_rag_eval_verification_query_text
        CHECK (btrim(query_text) <> ''),
    CONSTRAINT chk_kwb_rag_eval_verification_query_role
        CHECK (
            dataset_role IN (
                'promoted',
                'holdout',
                'baseline',
                'neighbour'
            )
        ),
    CONSTRAINT chk_kwb_rag_eval_verification_query_role_refs
        CHECK (
            (
                dataset_role = 'promoted'
                AND question_id IS NOT NULL
                AND promotion_id IS NOT NULL
            )
            OR (
                dataset_role IN ('holdout', 'baseline')
                AND question_id IS NOT NULL
                AND promotion_id IS NULL
            )
            OR (
                dataset_role = 'neighbour'
                AND promotion_id IS NULL
            )
        )
);

CREATE TABLE IF NOT EXISTS knowledge_workbench_rag_eval_verification_outcomes (
    verification_outcome_id TEXT PRIMARY KEY,
    verification_id TEXT NOT NULL
        REFERENCES knowledge_workbench_rag_eval_verifications(verification_id)
        ON DELETE CASCADE,
    verification_query_id TEXT NOT NULL
        REFERENCES knowledge_workbench_rag_eval_verification_queries(verification_query_id)
        ON DELETE CASCADE,
    revision_id TEXT NOT NULL
        REFERENCES knowledge_workbench_rag_eval_embedding_revisions(revision_id)
        ON DELETE RESTRICT,
    project_id UUID NOT NULL
        REFERENCES projects(id)
        ON DELETE RESTRICT,

    expected_runtime_entry_id TEXT NOT NULL,
    expected_fact_id TEXT NOT NULL,

    before_expected_rank INTEGER NULL,
    before_expected_score DOUBLE PRECISION NULL,
    before_best_competitor_runtime_entry_id TEXT NULL,
    before_best_competitor_fact_id TEXT NULL,
    before_best_competitor_score DOUBLE PRECISION NULL,
    before_score_margin DOUBLE PRECISION NULL,
    before_classification TEXT NOT NULL,

    after_expected_rank INTEGER NULL,
    after_expected_score DOUBLE PRECISION NULL,
    after_best_competitor_runtime_entry_id TEXT NULL,
    after_best_competitor_fact_id TEXT NULL,
    after_best_competitor_score DOUBLE PRECISION NULL,
    after_score_margin DOUBLE PRECISION NULL,
    after_classification TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL,

    CONSTRAINT uq_kwb_rag_eval_verification_outcome_query
        UNIQUE (verification_query_id),
    CONSTRAINT chk_kwb_rag_eval_verification_outcome_ranks
        CHECK (
            (before_expected_rank IS NULL OR before_expected_rank > 0)
            AND (after_expected_rank IS NULL OR after_expected_rank > 0)
        ),
    CONSTRAINT chk_kwb_rag_eval_verification_outcome_before_classification
        CHECK (
            before_classification IN (
                'pass_strong',
                'pass_weak',
                'confusion',
                'miss',
                'existing_alias_retrieval_failure'
            )
        ),
    CONSTRAINT chk_kwb_rag_eval_verification_outcome_after_classification
        CHECK (
            after_classification IN (
                'pass_strong',
                'pass_weak',
                'confusion',
                'miss',
                'existing_alias_retrieval_failure'
            )
        )
);

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_verifications_run
    ON knowledge_workbench_rag_eval_verifications (
        source_rag_eval_run_id,
        created_at,
        verification_id
    );

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_verifications_project_status
    ON knowledge_workbench_rag_eval_verifications (project_id, status);

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_verification_queries_role
    ON knowledge_workbench_rag_eval_verification_queries (
        verification_id,
        dataset_role
    );

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_verification_queries_expected
    ON knowledge_workbench_rag_eval_verification_queries (
        project_id,
        expected_runtime_entry_id
    );

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_verification_queries_question
    ON knowledge_workbench_rag_eval_verification_queries (question_id)
    WHERE question_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_verification_queries_promotion
    ON knowledge_workbench_rag_eval_verification_queries (promotion_id)
    WHERE promotion_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_verification_outcomes_verification
    ON knowledge_workbench_rag_eval_verification_outcomes (verification_id);

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_verification_outcomes_before
    ON knowledge_workbench_rag_eval_verification_outcomes (
        project_id,
        before_classification
    );

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_verification_outcomes_after
    ON knowledge_workbench_rag_eval_verification_outcomes (
        project_id,
        after_classification
    );
