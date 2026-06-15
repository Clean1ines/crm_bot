-- Knowledge Workbench Extraction stage progress index.
-- This table links generic Execution Runtime WorkItems to a concrete
-- claim-extraction workflow/stage without leaking Workbench lifecycle
-- semantics into execution_work_items.

CREATE TABLE IF NOT EXISTS claim_extraction_stage_work_items (
    workflow_run_id text NOT NULL,
    stage_run_id text NOT NULL,
    work_item_id text NOT NULL REFERENCES execution_work_items(work_item_id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),

    CONSTRAINT pk_claim_extraction_stage_work_items
        PRIMARY KEY (workflow_run_id, stage_run_id, work_item_id),

    CONSTRAINT chk_claim_extraction_stage_work_items_workflow_non_empty
        CHECK (length(trim(workflow_run_id)) > 0),

    CONSTRAINT chk_claim_extraction_stage_work_items_stage_non_empty
        CHECK (length(trim(stage_run_id)) > 0),

    CONSTRAINT chk_claim_extraction_stage_work_items_work_item_non_empty
        CHECK (length(trim(work_item_id)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_claim_extraction_stage_work_items_stage
    ON claim_extraction_stage_work_items (workflow_run_id, stage_run_id, created_at);

CREATE INDEX IF NOT EXISTS idx_claim_extraction_stage_work_items_work_item
    ON claim_extraction_stage_work_items (work_item_id);

-- Retired tail of this migration:
-- The pipeline_artifacts table belonged to the removed Artifact Runtime prototype.
-- Claim extraction progress now counts persisted draft_claim_observation_provenance rows.
-- Keep this no-op notice so ordered migration chains can pass without restoring
-- the retired pipeline_artifacts domain.
DO $$
BEGIN
    RAISE NOTICE '088 retired pipeline_artifacts stage payload index: pipeline_artifacts no longer exists';
END $$;
