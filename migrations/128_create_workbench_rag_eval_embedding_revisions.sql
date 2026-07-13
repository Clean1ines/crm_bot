CREATE TABLE IF NOT EXISTS knowledge_workbench_rag_eval_embedding_revisions (
    revision_id TEXT PRIMARY KEY,
    application_key TEXT NOT NULL UNIQUE,
    project_id UUID NOT NULL
        REFERENCES projects(id)
        ON DELETE RESTRICT,
    runtime_entry_id TEXT NOT NULL
        REFERENCES knowledge_workbench_runtime_retrieval_entries(runtime_entry_id)
        ON DELETE RESTRICT,
    source_rag_eval_run_id TEXT NOT NULL
        REFERENCES knowledge_workbench_rag_eval_runs(run_id)
        ON DELETE RESTRICT,

    promotion_ids JSONB NOT NULL,
    status TEXT NOT NULL,

    previous_embedding_text TEXT NOT NULL,
    new_embedding_text TEXT NOT NULL,

    previous_embedding vector(384) NOT NULL,
    new_embedding vector(384) NOT NULL,

    previous_promoted_questions JSONB NOT NULL,
    new_promoted_questions JSONB NOT NULL,

    embedding_model_id TEXT NOT NULL,
    embedding_dimensions INTEGER NOT NULL,

    previous_runtime_hash TEXT NOT NULL,
    new_runtime_hash TEXT NOT NULL,

    created_at TIMESTAMPTZ NOT NULL,
    accepted_at TIMESTAMPTZ NULL,
    regression_failed_at TIMESTAMPTZ NULL,
    rolled_back_at TIMESTAMPTZ NULL,

    CONSTRAINT chk_kwb_rag_eval_embedding_revision_status
        CHECK (
            status IN (
                'pending_verification',
                'accepted',
                'regression_failed',
                'rolled_back'
            )
        ),
    CONSTRAINT chk_kwb_rag_eval_embedding_revision_promotion_ids
        CHECK (
            jsonb_typeof(promotion_ids) = 'array'
            AND jsonb_array_length(promotion_ids) > 0
        ),
    CONSTRAINT chk_kwb_rag_eval_embedding_revision_previous_questions
        CHECK (jsonb_typeof(previous_promoted_questions) = 'array'),
    CONSTRAINT chk_kwb_rag_eval_embedding_revision_new_questions
        CHECK (jsonb_typeof(new_promoted_questions) = 'array'),
    CONSTRAINT chk_kwb_rag_eval_embedding_revision_dimensions
        CHECK (embedding_dimensions = 384),
    CONSTRAINT chk_kwb_rag_eval_embedding_revision_timestamps
        CHECK (
            (
                status = 'pending_verification'
                AND accepted_at IS NULL
                AND regression_failed_at IS NULL
                AND rolled_back_at IS NULL
            )
            OR (
                status = 'accepted'
                AND accepted_at IS NOT NULL
                AND regression_failed_at IS NULL
                AND rolled_back_at IS NULL
            )
            OR (
                status = 'regression_failed'
                AND accepted_at IS NULL
                AND regression_failed_at IS NOT NULL
                AND rolled_back_at IS NULL
            )
            OR (
                status = 'rolled_back'
                AND accepted_at IS NULL
                AND rolled_back_at IS NOT NULL
            )
        )
);

CREATE TABLE IF NOT EXISTS knowledge_workbench_rag_eval_promotion_application_claims (
    application_key TEXT PRIMARY KEY,
    project_id UUID NOT NULL
        REFERENCES projects(id)
        ON DELETE RESTRICT,
    runtime_entry_id TEXT NOT NULL
        REFERENCES knowledge_workbench_runtime_retrieval_entries(runtime_entry_id)
        ON DELETE RESTRICT,
    source_rag_eval_run_id TEXT NOT NULL
        REFERENCES knowledge_workbench_rag_eval_runs(run_id)
        ON DELETE RESTRICT,
    promotion_ids JSONB NOT NULL,
    previous_runtime_hash TEXT NOT NULL,

    status TEXT NOT NULL,
    lease_owner TEXT NOT NULL,
    lease_expires_at TIMESTAMPTZ NOT NULL,

    revision_id TEXT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ NULL,

    CONSTRAINT fk_kwb_rag_eval_promotion_application_claim_revision
        FOREIGN KEY (revision_id)
        REFERENCES knowledge_workbench_rag_eval_embedding_revisions(revision_id)
        ON DELETE RESTRICT
        DEFERRABLE INITIALLY DEFERRED,
    CONSTRAINT chk_kwb_rag_eval_promotion_application_claim_promotion_ids
        CHECK (
            jsonb_typeof(promotion_ids) = 'array'
            AND jsonb_array_length(promotion_ids) > 0
        ),
    CONSTRAINT chk_kwb_rag_eval_promotion_application_claim_status
        CHECK (status IN ('PREPARING', 'COMPLETED', 'FAILED')),
    CONSTRAINT chk_kwb_rag_eval_promotion_application_claim_state
        CHECK (
            (
                status = 'PREPARING'
                AND revision_id IS NULL
                AND completed_at IS NULL
            )
            OR (
                status = 'COMPLETED'
                AND revision_id IS NOT NULL
                AND completed_at IS NOT NULL
            )
            OR (
                status = 'FAILED'
                AND revision_id IS NULL
            )
        )
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_kwb_rag_eval_active_embedding_revision
    ON knowledge_workbench_rag_eval_embedding_revisions (
        project_id,
        runtime_entry_id
    )
    WHERE status = 'pending_verification';

CREATE UNIQUE INDEX IF NOT EXISTS uq_kwb_rag_eval_active_promotion_application_claim
    ON knowledge_workbench_rag_eval_promotion_application_claims (
        project_id,
        runtime_entry_id
    )
    WHERE status = 'PREPARING';

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_embedding_revisions_run
    ON knowledge_workbench_rag_eval_embedding_revisions (
        source_rag_eval_run_id,
        created_at,
        revision_id
    );

CREATE INDEX IF NOT EXISTS idx_kwb_rag_eval_promotion_application_claims_lease
    ON knowledge_workbench_rag_eval_promotion_application_claims (
        status,
        lease_expires_at,
        application_key
    );
