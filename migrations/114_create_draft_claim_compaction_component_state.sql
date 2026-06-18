CREATE TABLE IF NOT EXISTS draft_claim_compaction_components (
    component_ref text PRIMARY KEY,
    workflow_run_id text NOT NULL,
    group_ref text NOT NULL REFERENCES draft_claim_compaction_groups(group_ref) ON DELETE CASCADE,
    representative_node_ref text NOT NULL REFERENCES draft_claim_compaction_nodes(node_ref) ON DELETE CASCADE,
    active boolean NOT NULL,
    source_claim_refs jsonb NOT NULL,
    supersedes_component_refs jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT uq_draft_claim_compaction_components_workflow_group_component
        UNIQUE (workflow_run_id, group_ref, component_ref)
);

CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_components_workflow
    ON draft_claim_compaction_components (workflow_run_id);
CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_components_group
    ON draft_claim_compaction_components (group_ref);
CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_components_active
    ON draft_claim_compaction_components (workflow_run_id, group_ref, active);
CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_components_representative
    ON draft_claim_compaction_components (representative_node_ref);

CREATE TABLE IF NOT EXISTS draft_claim_compaction_component_incompatibilities (
    incompatibility_ref text PRIMARY KEY,
    workflow_run_id text NOT NULL,
    group_ref text NOT NULL REFERENCES draft_claim_compaction_groups(group_ref) ON DELETE CASCADE,
    left_component_ref text NOT NULL REFERENCES draft_claim_compaction_components(component_ref) ON DELETE CASCADE,
    right_component_ref text NOT NULL REFERENCES draft_claim_compaction_components(component_ref) ON DELETE CASCADE,
    source_comparison_ref text NULL REFERENCES draft_claim_compaction_comparisons(comparison_ref) ON DELETE SET NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT chk_draft_claim_compaction_component_incompatibilities_ordered
        CHECK (left_component_ref < right_component_ref),
    CONSTRAINT uq_draft_claim_compaction_component_incompatibilities_pair
        UNIQUE (workflow_run_id, group_ref, left_component_ref, right_component_ref)
);

CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_component_incompatibilities_workflow
    ON draft_claim_compaction_component_incompatibilities (workflow_run_id);
CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_component_incompatibilities_group
    ON draft_claim_compaction_component_incompatibilities (group_ref);
CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_component_incompatibilities_left
    ON draft_claim_compaction_component_incompatibilities (left_component_ref);
CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_component_incompatibilities_right
    ON draft_claim_compaction_component_incompatibilities (right_component_ref);
