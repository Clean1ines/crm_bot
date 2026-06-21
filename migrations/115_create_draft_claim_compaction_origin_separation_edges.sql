CREATE TABLE IF NOT EXISTS draft_claim_compaction_origin_separation_edges (
    separation_ref text PRIMARY KEY,
    workflow_run_id text NOT NULL,
    group_ref text NOT NULL REFERENCES draft_claim_compaction_groups(group_ref) ON DELETE CASCADE,
    origin_ref_a text NOT NULL,
    origin_ref_b text NOT NULL,
    established_by_batch_ref text NULL,
    established_by_work_item_id text NULL,
    established_by_dispatch_attempt_id text NULL,
    source_comparison_ref text NULL REFERENCES draft_claim_compaction_comparisons(comparison_ref) ON DELETE SET NULL,
    established_at timestamptz NOT NULL,
    CONSTRAINT chk_draft_claim_compaction_origin_separation_edges_ordered
        CHECK (origin_ref_a < origin_ref_b),
    CONSTRAINT uq_draft_claim_compaction_origin_separation_pair
        UNIQUE (workflow_run_id, group_ref, origin_ref_a, origin_ref_b)
);

CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_origin_separation_workflow
    ON draft_claim_compaction_origin_separation_edges (workflow_run_id);
CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_origin_separation_group
    ON draft_claim_compaction_origin_separation_edges (workflow_run_id, group_ref);
CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_origin_separation_left
    ON draft_claim_compaction_origin_separation_edges (origin_ref_a);
CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_origin_separation_right
    ON draft_claim_compaction_origin_separation_edges (origin_ref_b);
