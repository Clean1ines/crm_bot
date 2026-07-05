ALTER TABLE draft_claim_curation_workspaces
    DROP CONSTRAINT IF EXISTS draft_claim_curation_workspaces_status_check;

ALTER TABLE draft_claim_curation_workspaces
    ADD CONSTRAINT draft_claim_curation_workspaces_status_check
    CHECK (status IN ('draft', 'needs_republish', 'published'));
