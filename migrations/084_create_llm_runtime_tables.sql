-- Canonical LLM Runtime persistence.
-- Provider-neutral task/attempt state only.

CREATE TABLE IF NOT EXISTS llm_tasks (
    task_id text PRIMARY KEY,
    prompt_id text NOT NULL,
    prompt_version text NOT NULL,
    input_ref text NOT NULL,
    output_contract_ref text NOT NULL,
    status text NOT NULL,
    attempt_count integer NOT NULL DEFAULT 0,
    selected_provider_id text NULL,
    selected_model_id text NULL,
    selected_account_ref text NULL,
    wait_until timestamptz NULL,
    last_error_kind text NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_llm_tasks_id_non_empty
        CHECK (length(trim(task_id)) > 0),

    CONSTRAINT chk_llm_tasks_prompt_id_non_empty
        CHECK (length(trim(prompt_id)) > 0),

    CONSTRAINT chk_llm_tasks_prompt_version_non_empty
        CHECK (length(trim(prompt_version)) > 0),

    CONSTRAINT chk_llm_tasks_input_ref_non_empty
        CHECK (length(trim(input_ref)) > 0),

    CONSTRAINT chk_llm_tasks_output_contract_ref_non_empty
        CHECK (length(trim(output_contract_ref)) > 0),

    CONSTRAINT chk_llm_tasks_status
        CHECK (
            status IN (
                'ready',
                'running',
                'succeeded',
                'deferred',
                'retryable_failed',
                'terminal_failed',
                'cancelled'
            )
        ),

    CONSTRAINT chk_llm_tasks_attempt_count_non_negative
        CHECK (attempt_count >= 0),

    CONSTRAINT chk_llm_tasks_running_has_route
        CHECK (
            status <> 'running'
            OR (
                selected_provider_id IS NOT NULL
                AND selected_model_id IS NOT NULL
                AND selected_account_ref IS NOT NULL
            )
        ),

    CONSTRAINT chk_llm_tasks_wait_until_only_deferred
        CHECK (
            (
                status = 'deferred'
                AND wait_until IS NOT NULL
            )
            OR
            (
                status <> 'deferred'
                AND wait_until IS NULL
            )
        ),

    CONSTRAINT chk_llm_tasks_updated_after_created
        CHECK (updated_at >= created_at)
);

CREATE TABLE IF NOT EXISTS llm_attempts (
    attempt_id text PRIMARY KEY,
    task_id text NOT NULL REFERENCES llm_tasks(task_id) ON DELETE CASCADE,
    attempt_number integer NOT NULL,
    provider_id text NOT NULL,
    model_id text NOT NULL,
    account_ref text NOT NULL,
    started_at timestamptz NOT NULL,
    finished_at timestamptz NULL,
    input_tokens integer NULL,
    output_tokens integer NULL,
    error_kind text NULL,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT chk_llm_attempts_id_non_empty
        CHECK (length(trim(attempt_id)) > 0),

    CONSTRAINT chk_llm_attempts_task_id_non_empty
        CHECK (length(trim(task_id)) > 0),

    CONSTRAINT chk_llm_attempts_attempt_number_positive
        CHECK (attempt_number >= 1),

    CONSTRAINT chk_llm_attempts_provider_id_non_empty
        CHECK (length(trim(provider_id)) > 0),

    CONSTRAINT chk_llm_attempts_model_id_non_empty
        CHECK (length(trim(model_id)) > 0),

    CONSTRAINT chk_llm_attempts_account_ref_non_empty
        CHECK (length(trim(account_ref)) > 0),

    CONSTRAINT chk_llm_attempts_finished_after_started
        CHECK (finished_at IS NULL OR finished_at >= started_at),

    CONSTRAINT chk_llm_attempts_input_tokens_non_negative
        CHECK (input_tokens IS NULL OR input_tokens >= 0),

    CONSTRAINT chk_llm_attempts_output_tokens_non_negative
        CHECK (output_tokens IS NULL OR output_tokens >= 0),

    CONSTRAINT uq_llm_attempts_task_attempt
        UNIQUE (task_id, attempt_number)
);

CREATE INDEX IF NOT EXISTS idx_llm_tasks_status_wait
    ON llm_tasks (status, wait_until, updated_at);

CREATE INDEX IF NOT EXISTS idx_llm_tasks_prompt_input
    ON llm_tasks (prompt_id, input_ref);

CREATE INDEX IF NOT EXISTS idx_llm_attempts_task
    ON llm_attempts (task_id, attempt_number);
