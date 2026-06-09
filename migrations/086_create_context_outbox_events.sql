-- Generic bounded-context outbox.
-- This table is intentionally separate from older application event tables unless
-- their contract is explicitly proven compatible.

CREATE TABLE IF NOT EXISTS outbox_events (
    event_id text PRIMARY KEY,
    event_type text NOT NULL,
    aggregate_ref text NULL,
    payload jsonb NOT NULL,
    occurred_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    published_at timestamptz NULL,
    publish_attempt_count integer NOT NULL DEFAULT 0,
    last_publish_error text NULL,

    CONSTRAINT chk_outbox_events_id_non_empty
        CHECK (length(trim(event_id)) > 0),

    CONSTRAINT chk_outbox_events_type_non_empty
        CHECK (length(trim(event_type)) > 0),

    CONSTRAINT chk_outbox_events_payload_is_object
        CHECK (jsonb_typeof(payload) = 'object'),

    CONSTRAINT chk_outbox_events_publish_attempt_count_non_negative
        CHECK (publish_attempt_count >= 0),

    CONSTRAINT chk_outbox_events_published_after_created
        CHECK (published_at IS NULL OR published_at >= created_at)
);

CREATE INDEX IF NOT EXISTS idx_outbox_events_unpublished
    ON outbox_events (published_at, created_at)
    WHERE published_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_outbox_events_type_created
    ON outbox_events (event_type, created_at);
