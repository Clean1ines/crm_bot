CREATE TABLE IF NOT EXISTS draft_claim_curation_workspaces (
    workspace_ref text PRIMARY KEY,
    workflow_run_id text NOT NULL UNIQUE,
    project_id text NULL,
    source_document_ref text NULL,
    status text NOT NULL CHECK (status IN ('draft', 'published')),
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL
);

CREATE TABLE IF NOT EXISTS draft_claim_curation_items (
    item_ref text PRIMARY KEY,
    workspace_ref text NOT NULL REFERENCES draft_claim_curation_workspaces(workspace_ref) ON DELETE CASCADE,
    workflow_run_id text NOT NULL,
    group_ref text NOT NULL,
    compacted_node_ref text NOT NULL,
    source_claim_refs jsonb NOT NULL,
    original_payload jsonb NOT NULL,
    editable_payload jsonb NOT NULL,
    excluded boolean NOT NULL DEFAULT false,
    exclusion_reason text NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    UNIQUE (workspace_ref, compacted_node_ref)
);

CREATE INDEX IF NOT EXISTS idx_draft_claim_curation_items_workspace_ref
    ON draft_claim_curation_items(workspace_ref);

CREATE INDEX IF NOT EXISTS idx_draft_claim_curation_items_workflow_run_id
    ON draft_claim_curation_items(workflow_run_id);
