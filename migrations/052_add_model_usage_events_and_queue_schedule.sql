BEGIN;

CREATE TABLE IF NOT EXISTS model_usage_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    usage_type TEXT NOT NULL,
    source TEXT NOT NULL,
    tokens_input BIGINT NOT NULL DEFAULT 0,
    tokens_output BIGINT,
    tokens_total BIGINT NOT NULL DEFAULT 0,
    estimated_cost_usd DOUBLE PRECISION,
    document_id UUID REFERENCES knowledge_documents(id) ON DELETE SET NULL,
    thread_id UUID REFERENCES threads(id) ON DELETE SET NULL,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_model_usage_events_project_created_at
    ON model_usage_events(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_model_usage_events_project_source
    ON model_usage_events(project_id, source, usage_type);

ALTER TABLE execution_queue
    ADD COLUMN IF NOT EXISTS next_attempt_at TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS idx_queue_status_next_attempt_at
    ON execution_queue(status, next_attempt_at, created_at)
    WHERE status = 'pending';

ANALYZE model_usage_events;
ANALYZE execution_queue;

COMMIT;
