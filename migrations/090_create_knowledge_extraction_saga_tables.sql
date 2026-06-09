-- Canonical Knowledge Extraction Saga durable state persistence.
-- This stores only saga workflow state, phase checkpoints, command idempotency,
-- and event handling cursor rows. It does not wire workers or consumers.

CREATE TABLE IF NOT EXISTS knowledge_extraction_workflow_runs (
    workflow_run_id text PRIMARY KEY,
    project_id text NOT NULL,
    source_document_ref text NOT NULL,
    status text NOT NULL,
    current_phase text NOT NULL,
    pause_reason text NULL,
    failure_kind text NULL,
    failure_message text NULL,
    review_status text NULL,
    publication_ref text NULL,
    cleanup_status text NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    completed_at timestamptz NULL,
    cancelled_at timestamptz NULL,

    CONSTRAINT chk_knowledge_extraction_workflow_runs_id_non_empty
        CHECK (btrim(workflow_run_id) <> ''),

    CONSTRAINT chk_knowledge_extraction_workflow_runs_project_non_empty
        CHECK (btrim(project_id) <> ''),

    CONSTRAINT chk_knowledge_extraction_workflow_runs_source_document_non_empty
        CHECK (btrim(source_document_ref) <> ''),

    CONSTRAINT chk_knowledge_extraction_workflow_runs_status
        CHECK (
            status IN (
                'CREATED',
                'RUNNING',
                'PAUSED',
                'WAITING_FOR_EXTERNAL_EVENT',
                'WAITING_FOR_REVIEW',
                'FAILED',
                'CANCELLED',
                'COMPLETED'
            )
        ),

    CONSTRAINT chk_knowledge_extraction_workflow_runs_current_phase
        CHECK (
            current_phase IN (
                'DOCUMENT_ACCEPTED',
                'SOURCE_DOCUMENT_PERSISTED',
                'SOURCE_UNITS_CREATED',
                'PROMPT_A_WORK_SCHEDULED',
                'PROMPT_A_WORK_COMPLETED',
                'PROMPT_A_ARTIFACTS_APPLIED',
                'DRAFT_EMBEDDINGS_BUILT',
                'DRAFT_CLUSTERS_BUILT',
                'PROMPT_B_WORK_SCHEDULED',
                'PROMPT_B_WORK_COMPLETED',
                'FINAL_KNOWLEDGE_PREPARED',
                'WAITING_FOR_REVIEW',
                'REVIEW_COMPLETED',
                'PUBLISHED',
                'RETRIEVAL_EMBEDDINGS_BUILT',
                'INTERMEDIATE_ARTIFACTS_CLEANED',
                'DONE'
            )
        ),

    CONSTRAINT chk_knowledge_extraction_workflow_runs_completed_timestamp
        CHECK (status <> 'COMPLETED' OR completed_at IS NOT NULL),

    CONSTRAINT chk_knowledge_extraction_workflow_runs_cancelled_timestamp
        CHECK (status <> 'CANCELLED' OR cancelled_at IS NOT NULL),

    CONSTRAINT chk_knowledge_extraction_workflow_runs_failed_kind
        CHECK (
            status <> 'FAILED'
            OR (failure_kind IS NOT NULL AND btrim(failure_kind) <> '')
        ),

    CONSTRAINT chk_knowledge_extraction_workflow_runs_review_phase
        CHECK (
            status <> 'WAITING_FOR_REVIEW'
            OR current_phase = 'WAITING_FOR_REVIEW'
        ),

    CONSTRAINT chk_knowledge_extraction_workflow_runs_updated_after_created
        CHECK (updated_at >= created_at),

    CONSTRAINT chk_knowledge_extraction_workflow_runs_completed_after_created
        CHECK (completed_at IS NULL OR completed_at >= created_at),

    CONSTRAINT chk_knowledge_extraction_workflow_runs_cancelled_after_created
        CHECK (cancelled_at IS NULL OR cancelled_at >= created_at)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_extraction_workflow_runs_project
    ON knowledge_extraction_workflow_runs (project_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_extraction_workflow_runs_source_document
    ON knowledge_extraction_workflow_runs (source_document_ref);

CREATE INDEX IF NOT EXISTS idx_knowledge_extraction_workflow_runs_status_phase
    ON knowledge_extraction_workflow_runs (status, current_phase);

CREATE INDEX IF NOT EXISTS idx_knowledge_extraction_workflow_runs_updated_at
    ON knowledge_extraction_workflow_runs (updated_at);

CREATE TABLE IF NOT EXISTS knowledge_extraction_phase_checkpoints (
    workflow_run_id text NOT NULL REFERENCES knowledge_extraction_workflow_runs(workflow_run_id) ON DELETE CASCADE,
    phase_key text NOT NULL,
    phase_status text NOT NULL,
    expected_count integer NOT NULL DEFAULT 0,
    completed_count integer NOT NULL DEFAULT 0,
    failed_count integer NOT NULL DEFAULT 0,
    blocked_count integer NOT NULL DEFAULT 0,
    idempotency_key text NOT NULL DEFAULT '',
    last_event_ref text NULL,
    checkpoint_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    updated_at timestamptz NOT NULL,

    CONSTRAINT pk_knowledge_extraction_phase_checkpoints
        PRIMARY KEY (workflow_run_id, phase_key),

    CONSTRAINT chk_knowledge_extraction_phase_checkpoints_phase_key
        CHECK (
            phase_key IN (
                'DOCUMENT_ACCEPTED',
                'SOURCE_DOCUMENT_PERSISTED',
                'SOURCE_UNITS_CREATED',
                'PROMPT_A_WORK_SCHEDULED',
                'PROMPT_A_WORK_COMPLETED',
                'PROMPT_A_ARTIFACTS_APPLIED',
                'DRAFT_EMBEDDINGS_BUILT',
                'DRAFT_CLUSTERS_BUILT',
                'PROMPT_B_WORK_SCHEDULED',
                'PROMPT_B_WORK_COMPLETED',
                'FINAL_KNOWLEDGE_PREPARED',
                'WAITING_FOR_REVIEW',
                'REVIEW_COMPLETED',
                'PUBLISHED',
                'RETRIEVAL_EMBEDDINGS_BUILT',
                'INTERMEDIATE_ARTIFACTS_CLEANED',
                'DONE'
            )
        ),

    CONSTRAINT chk_knowledge_extraction_phase_checkpoints_phase_status
        CHECK (
            phase_status IN (
                'NOT_STARTED',
                'READY',
                'IN_PROGRESS',
                'WAITING',
                'BLOCKED',
                'COMPLETED',
                'SKIPPED',
                'FAILED',
                'CANCELLED'
            )
        ),

    CONSTRAINT chk_knowledge_extraction_phase_checkpoints_expected_non_negative
        CHECK (expected_count >= 0),

    CONSTRAINT chk_knowledge_extraction_phase_checkpoints_completed_non_negative
        CHECK (completed_count >= 0),

    CONSTRAINT chk_knowledge_extraction_phase_checkpoints_failed_non_negative
        CHECK (failed_count >= 0),

    CONSTRAINT chk_knowledge_extraction_phase_checkpoints_blocked_non_negative
        CHECK (blocked_count >= 0),

    CONSTRAINT chk_knowledge_extraction_phase_checkpoints_count_shape
        CHECK (
            expected_count = 0
            OR completed_count + failed_count + blocked_count <= expected_count
        ),

    CONSTRAINT chk_knowledge_extraction_phase_checkpoints_payload_is_object
        CHECK (jsonb_typeof(checkpoint_payload) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_knowledge_extraction_phase_checkpoints_phase_status
    ON knowledge_extraction_phase_checkpoints (phase_key, phase_status);

CREATE INDEX IF NOT EXISTS idx_knowledge_extraction_phase_checkpoints_updated_at
    ON knowledge_extraction_phase_checkpoints (updated_at);

CREATE TABLE IF NOT EXISTS knowledge_extraction_command_log (
    command_key text PRIMARY KEY,
    workflow_run_id text NOT NULL REFERENCES knowledge_extraction_workflow_runs(workflow_run_id) ON DELETE CASCADE,
    phase_key text NOT NULL,
    target_context text NOT NULL,
    command_kind text NOT NULL,
    command_payload_hash text NOT NULL,
    status text NOT NULL,
    emitted_at timestamptz NOT NULL,
    completed_at timestamptz NULL,
    result_ref text NULL,

    CONSTRAINT chk_knowledge_extraction_command_log_key_non_empty
        CHECK (btrim(command_key) <> ''),

    CONSTRAINT chk_knowledge_extraction_command_log_phase_key
        CHECK (
            phase_key IN (
                'DOCUMENT_ACCEPTED',
                'SOURCE_DOCUMENT_PERSISTED',
                'SOURCE_UNITS_CREATED',
                'PROMPT_A_WORK_SCHEDULED',
                'PROMPT_A_WORK_COMPLETED',
                'PROMPT_A_ARTIFACTS_APPLIED',
                'DRAFT_EMBEDDINGS_BUILT',
                'DRAFT_CLUSTERS_BUILT',
                'PROMPT_B_WORK_SCHEDULED',
                'PROMPT_B_WORK_COMPLETED',
                'FINAL_KNOWLEDGE_PREPARED',
                'WAITING_FOR_REVIEW',
                'REVIEW_COMPLETED',
                'PUBLISHED',
                'RETRIEVAL_EMBEDDINGS_BUILT',
                'INTERMEDIATE_ARTIFACTS_CLEANED',
                'DONE'
            )
        ),

    CONSTRAINT chk_knowledge_extraction_command_log_target_non_empty
        CHECK (btrim(target_context) <> ''),

    CONSTRAINT chk_knowledge_extraction_command_log_kind_non_empty
        CHECK (btrim(command_kind) <> ''),

    CONSTRAINT chk_knowledge_extraction_command_log_payload_hash_non_empty
        CHECK (btrim(command_payload_hash) <> ''),

    CONSTRAINT chk_knowledge_extraction_command_log_status_non_empty
        CHECK (btrim(status) <> ''),

    CONSTRAINT chk_knowledge_extraction_command_log_completed_after_emitted
        CHECK (completed_at IS NULL OR completed_at >= emitted_at)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_extraction_command_log_workflow_phase
    ON knowledge_extraction_command_log (workflow_run_id, phase_key);

CREATE INDEX IF NOT EXISTS idx_knowledge_extraction_command_log_target_kind
    ON knowledge_extraction_command_log (target_context, command_kind);

CREATE INDEX IF NOT EXISTS idx_knowledge_extraction_command_log_status
    ON knowledge_extraction_command_log (status);

CREATE INDEX IF NOT EXISTS idx_knowledge_extraction_command_log_emitted_at
    ON knowledge_extraction_command_log (emitted_at);

CREATE TABLE IF NOT EXISTS knowledge_extraction_event_cursor (
    consumer_name text NOT NULL,
    event_id text NOT NULL,
    workflow_run_id text NOT NULL REFERENCES knowledge_extraction_workflow_runs(workflow_run_id) ON DELETE CASCADE,
    event_type text NOT NULL,
    processed_at timestamptz NOT NULL,
    handler_result text NOT NULL,

    CONSTRAINT pk_knowledge_extraction_event_cursor
        PRIMARY KEY (consumer_name, event_id),

    CONSTRAINT chk_knowledge_extraction_event_cursor_consumer_non_empty
        CHECK (btrim(consumer_name) <> ''),

    CONSTRAINT chk_knowledge_extraction_event_cursor_event_non_empty
        CHECK (btrim(event_id) <> ''),

    CONSTRAINT chk_knowledge_extraction_event_cursor_type_non_empty
        CHECK (btrim(event_type) <> ''),

    CONSTRAINT chk_knowledge_extraction_event_cursor_result_non_empty
        CHECK (btrim(handler_result) <> '')
);

CREATE INDEX IF NOT EXISTS idx_knowledge_extraction_event_cursor_workflow
    ON knowledge_extraction_event_cursor (workflow_run_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_extraction_event_cursor_type_processed
    ON knowledge_extraction_event_cursor (event_type, processed_at);
