CREATE TABLE IF NOT EXISTS execution_work_item_attempt_dispatches (
    attempt_id text PRIMARY KEY
        REFERENCES execution_work_item_attempts(attempt_id)
        ON DELETE CASCADE,

    work_item_id text NOT NULL
        REFERENCES execution_work_items(work_item_id)
        ON DELETE CASCADE,

    attempt_number integer NOT NULL,
    lease_token text NOT NULL,
    worker_ref text NOT NULL,

    schedule_payload jsonb NOT NULL,
    llm_allocation_payload jsonb NOT NULL,
    dispatch_payload jsonb NOT NULL,

    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_execution_attempt_dispatches_attempt_id_non_empty
        CHECK (length(trim(attempt_id)) > 0),

    CONSTRAINT chk_execution_attempt_dispatches_work_item_id_non_empty
        CHECK (length(trim(work_item_id)) > 0),

    CONSTRAINT chk_execution_attempt_dispatches_attempt_number_positive
        CHECK (attempt_number >= 1),

    CONSTRAINT chk_execution_attempt_dispatches_lease_token_non_empty
        CHECK (length(trim(lease_token)) > 0),

    CONSTRAINT chk_execution_attempt_dispatches_worker_ref_non_empty
        CHECK (length(trim(worker_ref)) > 0),

    CONSTRAINT uq_execution_attempt_dispatches_work_item_attempt
        UNIQUE (work_item_id, attempt_number)
);

CREATE INDEX IF NOT EXISTS idx_execution_attempt_dispatches_work_item
    ON execution_work_item_attempt_dispatches (work_item_id, attempt_number);
