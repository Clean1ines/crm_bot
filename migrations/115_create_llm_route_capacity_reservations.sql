CREATE TABLE IF NOT EXISTS llm_route_capacity_reservations (
    attempt_id text PRIMARY KEY
        REFERENCES execution_work_item_attempts(attempt_id)
        ON DELETE CASCADE,
    provider text NOT NULL,
    account_ref text NOT NULL,
    model_ref text NOT NULL,
    reserved_requests integer NOT NULL,
    reserved_tokens integer NOT NULL,
    actual_tokens integer NULL,
    status text NOT NULL,
    expires_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL,
    finalized_at timestamptz NULL,

    CONSTRAINT chk_llm_route_capacity_reservations_route_non_empty
        CHECK (
            length(trim(provider)) > 0
            AND length(trim(account_ref)) > 0
            AND length(trim(model_ref)) > 0
        ),
    CONSTRAINT chk_llm_route_capacity_reservations_reserved_positive
        CHECK (reserved_requests > 0 AND reserved_tokens > 0),
    CONSTRAINT chk_llm_route_capacity_reservations_actual_non_negative
        CHECK (actual_tokens IS NULL OR actual_tokens >= 0),
    CONSTRAINT chk_llm_route_capacity_reservations_status
        CHECK (status IN ('active', 'committed', 'released')),
    CONSTRAINT chk_llm_route_capacity_reservations_expiry
        CHECK (expires_at > created_at),
    CONSTRAINT chk_llm_route_capacity_reservations_finalization
        CHECK (
            (status = 'active' AND finalized_at IS NULL)
            OR (status <> 'active' AND finalized_at IS NOT NULL)
        )
);

CREATE INDEX IF NOT EXISTS idx_llm_route_capacity_reservations_active_route
    ON llm_route_capacity_reservations (
        provider,
        account_ref,
        model_ref,
        expires_at
    )
    WHERE status = 'active';
