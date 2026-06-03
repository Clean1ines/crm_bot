CREATE TABLE IF NOT EXISTS knowledge_workbench_fact_registry_application_queue (
    queue_item_id text PRIMARY KEY,
    processing_run_id text NOT NULL,
    project_id uuid NOT NULL,
    document_id text NOT NULL,
    section_id text NOT NULL,
    fact_registry_node_run_id text NOT NULL,
    observed_registry_snapshot_id text NOT NULL,
    observed_registry_snapshot_sequence integer NOT NULL CHECK (observed_registry_snapshot_sequence > 0),
    claim_input_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    status text NOT NULL,
    claimed_by_worker_id text,
    lease_expires_at timestamptz,
    applied_registry_snapshot_id text,
    stale_at_registry_snapshot_id text,
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_workbench_fact_registry_application_queue_ready
    ON knowledge_workbench_fact_registry_application_queue (
        project_id,
        document_id,
        processing_run_id,
        status,
        observed_registry_snapshot_sequence,
        created_at
    );

CREATE INDEX IF NOT EXISTS idx_workbench_fact_registry_application_queue_section
    ON knowledge_workbench_fact_registry_application_queue (
        project_id,
        document_id,
        section_id
    );

CREATE INDEX IF NOT EXISTS idx_workbench_fact_registry_application_queue_snapshot
    ON knowledge_workbench_fact_registry_application_queue (
        project_id,
        document_id,
        processing_run_id,
        observed_registry_snapshot_id
    );
