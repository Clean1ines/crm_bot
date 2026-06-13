-- Knowledge Workbench Extraction draft claim observation provenance persistence.
-- Stores Prompt A trace refs without adding DB-level dependencies to runtime contexts.

CREATE TABLE IF NOT EXISTS draft_claim_observation_provenance (
    observation_ref text PRIMARY KEY REFERENCES draft_claim_observations(observation_ref) ON DELETE CASCADE,
    source_unit_ref text NOT NULL,
    workflow_run_id text NOT NULL,
    stage_run_id text NOT NULL,
    work_item_id text NOT NULL,
    work_item_attempt_id text NOT NULL,
    llm_task_id text NOT NULL,
    llm_attempt_id text NOT NULL,
    prompt_id text NOT NULL,
    prompt_version text NOT NULL,
    claim_index integer NOT NULL,
    created_at timestamptz NOT NULL,

    CONSTRAINT chk_draft_claim_observation_provenance_observation_ref_non_empty
        CHECK (length(trim(observation_ref)) > 0),

    CONSTRAINT chk_draft_claim_observation_provenance_source_unit_ref_non_empty
        CHECK (length(trim(source_unit_ref)) > 0),

    CONSTRAINT chk_draft_claim_observation_provenance_workflow_run_id_non_empty
        CHECK (length(trim(workflow_run_id)) > 0),

    CONSTRAINT chk_draft_claim_observation_provenance_stage_run_id_non_empty
        CHECK (length(trim(stage_run_id)) > 0),

    CONSTRAINT chk_draft_claim_observation_provenance_work_item_id_non_empty
        CHECK (length(trim(work_item_id)) > 0),

    CONSTRAINT chk_draft_claim_observation_provenance_work_item_attempt_id_non_empty
        CHECK (length(trim(work_item_attempt_id)) > 0),

    CONSTRAINT chk_draft_claim_observation_provenance_llm_task_id_non_empty
        CHECK (length(trim(llm_task_id)) > 0),

    CONSTRAINT chk_draft_claim_observation_provenance_llm_attempt_id_non_empty
        CHECK (length(trim(llm_attempt_id)) > 0),

    CONSTRAINT chk_draft_claim_observation_provenance_prompt_id_non_empty
        CHECK (length(trim(prompt_id)) > 0),

    CONSTRAINT chk_draft_claim_observation_provenance_prompt_version_non_empty
        CHECK (length(trim(prompt_version)) > 0),

    CONSTRAINT chk_draft_claim_observation_provenance_claim_index_non_negative
        CHECK (claim_index >= 0)
);

CREATE INDEX IF NOT EXISTS idx_draft_claim_observation_provenance_stage
    ON draft_claim_observation_provenance (workflow_run_id, stage_run_id, claim_index);

CREATE INDEX IF NOT EXISTS idx_draft_claim_observation_provenance_source_unit
    ON draft_claim_observation_provenance (source_unit_ref, claim_index);

CREATE INDEX IF NOT EXISTS idx_draft_claim_observation_provenance_work_item
    ON draft_claim_observation_provenance (work_item_id);

CREATE INDEX IF NOT EXISTS idx_draft_claim_observation_provenance_llm_task
    ON draft_claim_observation_provenance (llm_task_id);
