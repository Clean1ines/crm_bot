CREATE TABLE IF NOT EXISTS llm_attempt_capacity_observations (
    observation_id text PRIMARY KEY,
    provider text NOT NULL,
    account_ref text NOT NULL,
    model_ref text NOT NULL,
    remaining_minute_requests integer NULL,
    remaining_minute_tokens integer NULL,
    remaining_daily_requests integer NULL,
    remaining_daily_tokens integer NULL,
    minute_reset_at timestamptz NULL,
    daily_reset_at timestamptz NULL,
    actual_prompt_tokens integer NULL,
    actual_completion_tokens integer NULL,
    actual_total_tokens integer NULL,
    outcome_class text NOT NULL,
    observed_at timestamptz NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_llm_attempt_capacity_observations_provider_non_empty
        CHECK (length(trim(provider)) > 0),
    CONSTRAINT chk_llm_attempt_capacity_observations_account_ref_non_empty
        CHECK (length(trim(account_ref)) > 0),
    CONSTRAINT chk_llm_attempt_capacity_observations_model_ref_non_empty
        CHECK (length(trim(model_ref)) > 0),
    CONSTRAINT chk_llm_attempt_capacity_observations_outcome_class_non_empty
        CHECK (length(trim(outcome_class)) > 0),
    CONSTRAINT chk_llm_attempt_capacity_observations_remaining_minute_requests_non_negative
        CHECK (remaining_minute_requests IS NULL OR remaining_minute_requests >= 0),
    CONSTRAINT chk_llm_attempt_capacity_observations_remaining_minute_tokens_non_negative
        CHECK (remaining_minute_tokens IS NULL OR remaining_minute_tokens >= 0),
    CONSTRAINT chk_llm_attempt_capacity_observations_remaining_daily_requests_non_negative
        CHECK (remaining_daily_requests IS NULL OR remaining_daily_requests >= 0),
    CONSTRAINT chk_llm_attempt_capacity_observations_remaining_daily_tokens_non_negative
        CHECK (remaining_daily_tokens IS NULL OR remaining_daily_tokens >= 0),
    CONSTRAINT chk_llm_attempt_capacity_observations_actual_prompt_tokens_non_negative
        CHECK (actual_prompt_tokens IS NULL OR actual_prompt_tokens >= 0),
    CONSTRAINT chk_llm_attempt_capacity_observations_actual_completion_tokens_non_negative
        CHECK (actual_completion_tokens IS NULL OR actual_completion_tokens >= 0),
    CONSTRAINT chk_llm_attempt_capacity_observations_actual_total_tokens_non_negative
        CHECK (actual_total_tokens IS NULL OR actual_total_tokens >= 0)
);

CREATE INDEX IF NOT EXISTS idx_llm_attempt_capacity_observations_provider_account_model
    ON llm_attempt_capacity_observations (
        provider,
        account_ref,
        model_ref,
        observed_at DESC
    );

CREATE INDEX IF NOT EXISTS idx_llm_attempt_capacity_observations_observed_at
    ON llm_attempt_capacity_observations (observed_at DESC);
