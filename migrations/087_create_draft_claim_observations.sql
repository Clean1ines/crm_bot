-- Knowledge Workbench Extraction draft claim observation persistence.
-- Prompt A draft only. Later-stage consolidation/publication concepts belong elsewhere.

CREATE TABLE IF NOT EXISTS draft_claim_observations (
    observation_ref text PRIMARY KEY,
    source_unit_ref text NOT NULL,
    claim text NOT NULL,
    granularity text NOT NULL,
    exclusion_scope text NOT NULL DEFAULT '',
    evidence_block text NOT NULL,
    created_at timestamptz NOT NULL,

    CONSTRAINT chk_draft_claim_observations_ref_non_empty
        CHECK (length(trim(observation_ref)) > 0),

    CONSTRAINT chk_draft_claim_observations_source_unit_ref_non_empty
        CHECK (length(trim(source_unit_ref)) > 0),

    CONSTRAINT chk_draft_claim_observations_claim_non_empty
        CHECK (length(trim(claim)) > 0),

    CONSTRAINT chk_draft_claim_observations_granularity
        CHECK (granularity IN ('atomic', 'composite')),

    CONSTRAINT chk_draft_claim_observations_exclusion_scope_not_null
        CHECK (exclusion_scope IS NOT NULL),

    CONSTRAINT chk_draft_claim_observations_evidence_block_non_empty
        CHECK (length(trim(evidence_block)) > 0)
);

CREATE TABLE IF NOT EXISTS draft_claim_observation_possible_questions (
    observation_ref text NOT NULL REFERENCES draft_claim_observations(observation_ref) ON DELETE CASCADE,
    ordinal integer NOT NULL,
    question text NOT NULL,

    CONSTRAINT pk_draft_claim_observation_possible_questions
        PRIMARY KEY (observation_ref, ordinal),

    CONSTRAINT chk_draft_claim_observation_questions_ordinal_non_negative
        CHECK (ordinal >= 0),

    CONSTRAINT chk_draft_claim_observation_questions_question_non_empty
        CHECK (length(trim(question)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_draft_claim_observations_source_unit
    ON draft_claim_observations (source_unit_ref, created_at);

CREATE INDEX IF NOT EXISTS idx_draft_claim_observation_questions_observation
    ON draft_claim_observation_possible_questions (observation_ref, ordinal);
