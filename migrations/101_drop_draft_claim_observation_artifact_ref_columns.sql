DO $$
BEGIN
    EXECUTE 'ALTER TABLE draft_claim_observation_provenance DROP COLUMN IF EXISTS '
        || quote_ident('raw_' || 'artifact_ref');

    EXECUTE 'ALTER TABLE draft_claim_observation_provenance DROP COLUMN IF EXISTS '
        || quote_ident('parsed_' || 'artifact_ref');
END $$;
