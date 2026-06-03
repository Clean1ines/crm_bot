CREATE TABLE IF NOT EXISTS knowledge_workbench_parallel_section_batch_plans (
    batch_plan_id text PRIMARY KEY,
    processing_run_id text NOT NULL,
    project_id uuid NOT NULL,
    document_id text NOT NULL,
    observed_registry_snapshot_id text NOT NULL,
    observed_registry_snapshot_sequence integer NOT NULL CHECK (observed_registry_snapshot_sequence > 0),
    max_lanes integer NOT NULL CHECK (max_lanes > 0),
    lanes_payload jsonb NOT NULL,
    queue_item_count integer NOT NULL CHECK (queue_item_count >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_workbench_parallel_section_batch_plans_run
    ON knowledge_workbench_parallel_section_batch_plans (
        project_id,
        document_id,
        processing_run_id
    );

CREATE TABLE IF NOT EXISTS knowledge_workbench_section_batch_queue_items (
    queue_item_id text PRIMARY KEY,
    batch_plan_id text NOT NULL REFERENCES knowledge_workbench_parallel_section_batch_plans(batch_plan_id) ON DELETE CASCADE,
    processing_run_id text NOT NULL,
    project_id uuid NOT NULL,
    document_id text NOT NULL,
    section_id text NOT NULL,
    section_key text NOT NULL,
    section_index integer NOT NULL CHECK (section_index >= 0),
    lane_id text NOT NULL,
    lane_index integer NOT NULL CHECK (lane_index >= 0),
    observed_registry_snapshot_id text NOT NULL,
    observed_registry_snapshot_sequence integer NOT NULL CHECK (observed_registry_snapshot_sequence > 0),
    status text NOT NULL,
    claimed_by_worker_id text,
    lease_expires_at timestamptz,
    claim_observations_node_run_id text,
    fact_registry_application_queue_item_id text,
    error_kind text,
    attempt_count integer NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz
);

CREATE INDEX IF NOT EXISTS idx_workbench_section_batch_queue_run_status
    ON knowledge_workbench_section_batch_queue_items (
        project_id,
        document_id,
        processing_run_id,
        status,
        lane_index,
        section_index
    );

CREATE INDEX IF NOT EXISTS idx_workbench_section_batch_queue_plan
    ON knowledge_workbench_section_batch_queue_items (
        batch_plan_id,
        lane_index,
        section_index
    );
