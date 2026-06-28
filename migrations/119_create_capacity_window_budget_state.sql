CREATE TABLE IF NOT EXISTS capacity_window_budget_state (
    provider TEXT NOT NULL,
    account_ref TEXT NULL,
    model_ref TEXT NOT NULL,
    minute_reset_at TIMESTAMPTZ NULL,
    daily_reset_at TIMESTAMPTZ NULL,
    remaining_minute_requests INTEGER NULL,
    remaining_minute_tokens INTEGER NULL,
    remaining_daily_requests INTEGER NULL,
    remaining_daily_tokens INTEGER NULL,
    reserved_minute_requests INTEGER NOT NULL DEFAULT 0,
    reserved_minute_tokens INTEGER NOT NULL DEFAULT 0,
    reserved_daily_requests INTEGER NOT NULL DEFAULT 0,
    reserved_daily_tokens INTEGER NOT NULL DEFAULT 0,
    frozen_until TIMESTAMPTZ NULL,
    created_at TIMESTAMPTZ NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (provider, account_ref, model_ref),
    CONSTRAINT chk_capacity_window_budget_state_non_empty_text
        CHECK (
            length(trim(provider)) > 0
            AND length(trim(model_ref)) > 0
            AND (
                account_ref IS NULL
                OR length(trim(account_ref)) > 0
            )
        ),
    CONSTRAINT chk_capacity_window_budget_state_non_negative_reserved
        CHECK (
            reserved_minute_requests >= 0
            AND reserved_minute_tokens >= 0
            AND reserved_daily_requests >= 0
            AND reserved_daily_tokens >= 0
        ),
    CONSTRAINT chk_capacity_window_budget_state_nullable_remaining_non_negative
        CHECK (
            (remaining_minute_requests IS NULL OR remaining_minute_requests >= 0)
            AND (remaining_minute_tokens IS NULL OR remaining_minute_tokens >= 0)
            AND (remaining_daily_requests IS NULL OR remaining_daily_requests >= 0)
            AND (remaining_daily_tokens IS NULL OR remaining_daily_tokens >= 0)
        )
);
