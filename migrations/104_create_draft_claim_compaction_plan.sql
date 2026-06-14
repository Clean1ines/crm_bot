CREATE TABLE IF NOT EXISTS draft_claim_compaction_candidate_edges (
    edge_ref text PRIMARY KEY,
    workflow_run_id text NOT NULL,
    source_document_ref text NOT NULL,
    left_observation_ref text NOT NULL REFERENCES draft_claim_observations(observation_ref) ON DELETE CASCADE,
    right_observation_ref text NOT NULL REFERENCES draft_claim_observations(observation_ref) ON DELETE CASCADE,
    left_embedding_ref text NOT NULL REFERENCES draft_claim_embeddings(embedding_ref) ON DELETE CASCADE,
    right_embedding_ref text NOT NULL REFERENCES draft_claim_embeddings(embedding_ref) ON DELETE CASCADE,
    vector_score double precision NOT NULL CHECK (vector_score >= 0 AND vector_score <= 1),
    lexical_score double precision NOT NULL CHECK (lexical_score >= 0 AND lexical_score <= 1),
    question_overlap_score double precision NOT NULL CHECK (question_overlap_score >= 0 AND question_overlap_score <= 1),
    exclusion_scope_score double precision NOT NULL CHECK (exclusion_scope_score >= 0 AND exclusion_scope_score <= 1),
    granularity_score double precision NOT NULL CHECK (granularity_score >= 0 AND granularity_score <= 1),
    combined_score double precision NOT NULL CHECK (combined_score >= 0 AND combined_score <= 1),
    signals jsonb NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT chk_draft_claim_compaction_candidate_edges_ordered
        CHECK (left_observation_ref < right_observation_ref),
    CONSTRAINT uq_draft_claim_compaction_candidate_edges_pair
        UNIQUE (workflow_run_id, left_observation_ref, right_observation_ref)
);

CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_candidate_edges_workflow
    ON draft_claim_compaction_candidate_edges (workflow_run_id);
CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_candidate_edges_source_document
    ON draft_claim_compaction_candidate_edges (source_document_ref);
CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_candidate_edges_score
    ON draft_claim_compaction_candidate_edges (workflow_run_id, combined_score DESC);
CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_candidate_edges_left
    ON draft_claim_compaction_candidate_edges (left_observation_ref);
CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_candidate_edges_right
    ON draft_claim_compaction_candidate_edges (right_observation_ref);

CREATE TABLE IF NOT EXISTS draft_claim_compaction_groups (
    group_ref text PRIMARY KEY,
    workflow_run_id text NOT NULL,
    source_document_ref text NOT NULL,
    embedding_model_id text NOT NULL,
    group_algorithm text NOT NULL,
    group_threshold double precision NOT NULL CHECK (group_threshold >= 0 AND group_threshold <= 1),
    member_count integer NOT NULL CHECK (member_count > 0),
    estimated_input_tokens integer NOT NULL CHECK (estimated_input_tokens >= 0),
    requires_split boolean NOT NULL,
    created_at timestamptz NOT NULL,
    CONSTRAINT uq_draft_claim_compaction_groups_workflow_group
        UNIQUE (workflow_run_id, group_ref)
);

CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_groups_workflow
    ON draft_claim_compaction_groups (workflow_run_id);
CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_groups_source_document
    ON draft_claim_compaction_groups (source_document_ref);

CREATE TABLE IF NOT EXISTS draft_claim_compaction_group_members (
    group_ref text NOT NULL REFERENCES draft_claim_compaction_groups(group_ref) ON DELETE CASCADE,
    observation_ref text NOT NULL REFERENCES draft_claim_observations(observation_ref) ON DELETE CASCADE,
    embedding_ref text NOT NULL REFERENCES draft_claim_embeddings(embedding_ref) ON DELETE CASCADE,
    source_unit_ref text NOT NULL,
    member_rank integer NOT NULL CHECK (member_rank >= 0),
    member_kind text NOT NULL DEFAULT 'draft_claim',
    created_at timestamptz NOT NULL,
    PRIMARY KEY (group_ref, observation_ref)
);

CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_group_members_observation
    ON draft_claim_compaction_group_members (observation_ref);
CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_group_members_embedding
    ON draft_claim_compaction_group_members (embedding_ref);

CREATE TABLE IF NOT EXISTS draft_claim_compaction_batches (
    batch_ref text PRIMARY KEY,
    workflow_run_id text NOT NULL,
    group_ref text NOT NULL REFERENCES draft_claim_compaction_groups(group_ref) ON DELETE CASCADE,
    prompt_variant text NOT NULL,
    model_id text NOT NULL,
    estimated_input_tokens integer NOT NULL CHECK (estimated_input_tokens >= 0),
    batch_status text NOT NULL,
    member_count integer NOT NULL CHECK (member_count > 0),
    created_at timestamptz NOT NULL,
    CONSTRAINT uq_draft_claim_compaction_batches_workflow_group_batch
        UNIQUE (workflow_run_id, group_ref, batch_ref)
);

CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_batches_workflow
    ON draft_claim_compaction_batches (workflow_run_id);
CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_batches_group
    ON draft_claim_compaction_batches (group_ref);
CREATE INDEX IF NOT EXISTS idx_draft_claim_compaction_batches_status
    ON draft_claim_compaction_batches (workflow_run_id, batch_status);
