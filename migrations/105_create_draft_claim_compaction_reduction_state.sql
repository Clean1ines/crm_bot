CREATE TABLE IF NOT EXISTS draft_claim_compaction_nodes (
    node_ref text PRIMARY KEY,
    workflow_run_id text NOT NULL,
    group_ref text NOT NULL REFERENCES draft_claim_compaction_groups(group_ref) ON DELETE CASCADE,
    node_kind text NOT NULL,
    active boolean NOT NULL,
    source_claim_refs jsonb NOT NULL,
    supersedes_node_refs jsonb NOT NULL,
    estimated_input_tokens integer NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT chk_draft_claim_compaction_nodes_kind
        CHECK (node_kind IN ('raw', 'compacted')),
    CONSTRAINT chk_draft_claim_compaction_nodes_estimated_input_tokens
        CHECK (estimated_input_tokens >= 0),
    CONSTRAINT uq_draft_claim_compaction_nodes_workflow_group_node
        UNIQUE (workflow_run_id, group_ref, node_ref)
);

CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_nodes_workflow
    ON draft_claim_compaction_nodes (workflow_run_id);
CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_nodes_group
    ON draft_claim_compaction_nodes (group_ref);
CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_nodes_active
    ON draft_claim_compaction_nodes (active);
CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_nodes_kind
    ON draft_claim_compaction_nodes (node_kind);

CREATE TABLE IF NOT EXISTS draft_claim_compaction_node_sources (
    node_ref text NOT NULL REFERENCES draft_claim_compaction_nodes(node_ref) ON DELETE CASCADE,
    source_ref text NOT NULL,
    source_kind text NOT NULL,
    created_at timestamptz NOT NULL,
    PRIMARY KEY (node_ref, source_ref),
    CONSTRAINT chk_draft_claim_compaction_node_sources_kind
        CHECK (source_kind IN ('raw', 'compacted'))
);

CREATE TABLE IF NOT EXISTS draft_claim_compaction_rounds (
    round_ref text PRIMARY KEY,
    workflow_run_id text NOT NULL,
    group_ref text NOT NULL REFERENCES draft_claim_compaction_groups(group_ref) ON DELETE CASCADE,
    round_index integer NOT NULL,
    round_status text NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT chk_draft_claim_compaction_rounds_index
        CHECK (round_index >= 0),
    CONSTRAINT chk_draft_claim_compaction_rounds_status
        CHECK (round_status IN ('planned', 'running', 'completed', 'waiting_user_model_choice')),
    CONSTRAINT uq_draft_claim_compaction_rounds_workflow_group_round
        UNIQUE (workflow_run_id, group_ref, round_index)
);

CREATE TABLE IF NOT EXISTS draft_claim_compaction_comparisons (
    comparison_ref text PRIMARY KEY,
    workflow_run_id text NOT NULL,
    group_ref text NOT NULL REFERENCES draft_claim_compaction_groups(group_ref) ON DELETE CASCADE,
    left_node_ref text NOT NULL REFERENCES draft_claim_compaction_nodes(node_ref) ON DELETE CASCADE,
    right_node_ref text NOT NULL REFERENCES draft_claim_compaction_nodes(node_ref) ON DELETE CASCADE,
    status text NOT NULL,
    result_node_ref text NULL REFERENCES draft_claim_compaction_nodes(node_ref) ON DELETE SET NULL,
    round_index integer NOT NULL,
    created_at timestamptz NOT NULL,
    updated_at timestamptz NOT NULL,
    CONSTRAINT chk_draft_claim_compaction_comparisons_ordered
        CHECK (left_node_ref < right_node_ref),
    CONSTRAINT chk_draft_claim_compaction_comparisons_status
        CHECK (
            status IN (
                'pending',
                'merged',
                'not_merged',
                'too_large_for_primary_model',
                'waiting_user_model_choice',
                'superseded'
            )
        ),
    CONSTRAINT chk_draft_claim_compaction_comparisons_round_index
        CHECK (round_index >= 0),
    CONSTRAINT uq_draft_claim_compaction_comparisons_workflow_group_pair_round
        UNIQUE (workflow_run_id, group_ref, left_node_ref, right_node_ref, round_index)
);

CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_comparisons_workflow
    ON draft_claim_compaction_comparisons (workflow_run_id);
CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_comparisons_group
    ON draft_claim_compaction_comparisons (group_ref);
CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_comparisons_status
    ON draft_claim_compaction_comparisons (status);
CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_comparisons_round_index
    ON draft_claim_compaction_comparisons (round_index);
