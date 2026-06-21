CREATE TABLE IF NOT EXISTS frontend_workflow_events (
    projection_event_id TEXT PRIMARY KEY,
    source_event_id TEXT NOT NULL,
    source_sequence_number BIGINT NOT NULL,
    projection_version INTEGER NOT NULL,
    projection_type TEXT NOT NULL,
    event_type TEXT NOT NULL,
    operation_key TEXT NULL,
    canonical_phase TEXT NOT NULL,
    workflow_run_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    document_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    occurred_at TIMESTAMPTZ NOT NULL,
    causation_command_id TEXT NULL,
    correlation_id TEXT NULL,
    projected_at TIMESTAMPTZ NOT NULL,
    CONSTRAINT frontend_workflow_events_source_sequence_positive
        CHECK (source_sequence_number > 0),
    CONSTRAINT frontend_workflow_events_projection_version_positive
        CHECK (projection_version > 0),
    CONSTRAINT frontend_workflow_events_payload_object
        CHECK (jsonb_typeof(payload) = 'object'),
    CONSTRAINT frontend_workflow_events_projection_event_id_non_empty
        CHECK (length(trim(projection_event_id)) > 0),
    CONSTRAINT frontend_workflow_events_source_event_id_non_empty
        CHECK (length(trim(source_event_id)) > 0),
    CONSTRAINT frontend_workflow_events_projection_type_non_empty
        CHECK (length(trim(projection_type)) > 0),
    CONSTRAINT frontend_workflow_events_event_type_non_empty
        CHECK (length(trim(event_type)) > 0),
    CONSTRAINT frontend_workflow_events_canonical_phase_non_empty
        CHECK (length(trim(canonical_phase)) > 0),
    CONSTRAINT frontend_workflow_events_workflow_run_id_non_empty
        CHECK (length(trim(workflow_run_id)) > 0),
    CONSTRAINT frontend_workflow_events_project_id_non_empty
        CHECK (length(trim(project_id)) > 0),
    CONSTRAINT frontend_workflow_events_document_id_non_empty
        CHECK (length(trim(document_id)) > 0),
    CONSTRAINT frontend_workflow_events_operation_key_non_empty
        CHECK (operation_key IS NULL OR length(trim(operation_key)) > 0),
    CONSTRAINT frontend_workflow_events_causation_command_id_non_empty
        CHECK (
            causation_command_id IS NULL
            OR length(trim(causation_command_id)) > 0
        ),
    CONSTRAINT frontend_workflow_events_correlation_id_non_empty
        CHECK (correlation_id IS NULL OR length(trim(correlation_id)) > 0),
    CONSTRAINT frontend_workflow_events_source_projection_unique
        UNIQUE (source_event_id, projection_type, projection_version)
);

CREATE INDEX IF NOT EXISTS idx_frontend_workflow_events_project_source_sequence
    ON frontend_workflow_events (
        project_id,
        source_sequence_number,
        projection_type,
        projection_version,
        projection_event_id
    );

CREATE INDEX IF NOT EXISTS idx_frontend_workflow_events_workflow_source_sequence
    ON frontend_workflow_events (
        workflow_run_id,
        source_sequence_number,
        projection_type,
        projection_version,
        projection_event_id
    );

CREATE INDEX IF NOT EXISTS idx_frontend_workflow_events_document_source_sequence
    ON frontend_workflow_events (
        project_id,
        document_id,
        source_sequence_number,
        projection_type,
        projection_version,
        projection_event_id
    );

CREATE INDEX IF NOT EXISTS idx_frontend_workflow_events_projected_at
    ON frontend_workflow_events (projected_at);
