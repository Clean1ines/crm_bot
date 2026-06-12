ALTER TABLE draft_claim_observation_provenance
    ALTER COLUMN raw_artifact_ref DROP NOT NULL,
    ALTER COLUMN parsed_artifact_ref DROP NOT NULL;
