CREATE TABLE IF NOT EXISTS execution_work_item_schedules (
    work_item_id text PRIMARY KEY
        REFERENCES execution_work_items(work_item_id)
        ON DELETE CASCADE,
    idempotency_key text NOT NULL,
    payload_hash text NOT NULL,
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_execution_work_item_schedules_work_item_id_non_empty
        CHECK (length(trim(work_item_id)) > 0),

    CONSTRAINT chk_execution_work_item_schedules_idempotency_key_non_empty
        CHECK (length(trim(idempotency_key)) > 0),

    CONSTRAINT chk_execution_work_item_schedules_payload_hash_non_empty
        CHECK (length(trim(payload_hash)) > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_execution_work_item_schedules_idempotency_key
    ON execution_work_item_schedules (idempotency_key);