DROP INDEX IF EXISTS idx_queue_status_next_attempt_at;

ALTER TABLE execution_queue
    DROP COLUMN IF EXISTS next_attempt_at;

CREATE INDEX IF NOT EXISTS idx_queue_status_created_at
    ON execution_queue(status, created_at)
    WHERE status = 'pending';
