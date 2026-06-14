CREATE TABLE IF NOT EXISTS draft_claim_cluster_previews (
    workflow_run_id text PRIMARY KEY,
    preview_payload jsonb NOT NULL,
    claim_count integer NOT NULL,
    group_count integer NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);
