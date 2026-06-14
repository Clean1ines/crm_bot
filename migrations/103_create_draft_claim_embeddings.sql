-- Knowledge Workbench Extraction draft claim embedding persistence.
-- Workbench owns draft claim embedding persistence; embedding_runtime owns vector generation only.

CREATE TABLE IF NOT EXISTS draft_claim_embeddings (
    embedding_ref text PRIMARY KEY,
    workflow_run_id text NOT NULL,
    source_document_ref text NOT NULL,
    source_unit_ref text NOT NULL,
    observation_ref text NOT NULL REFERENCES draft_claim_observations(observation_ref) ON DELETE CASCADE,
    embedding_text text NOT NULL,
    embedding_text_hash text NOT NULL,
    embedding_model_id text NOT NULL,
    dimensions integer NOT NULL,
    embedding vector(384) NOT NULL,
    created_at timestamptz NOT NULL,

    CONSTRAINT chk_draft_claim_embeddings_ref_non_empty
        CHECK (length(trim(embedding_ref)) > 0),

    CONSTRAINT chk_draft_claim_embeddings_workflow_run_id_non_empty
        CHECK (length(trim(workflow_run_id)) > 0),

    CONSTRAINT chk_draft_claim_embeddings_source_document_ref_non_empty
        CHECK (length(trim(source_document_ref)) > 0),

    CONSTRAINT chk_draft_claim_embeddings_source_unit_ref_non_empty
        CHECK (length(trim(source_unit_ref)) > 0),

    CONSTRAINT chk_draft_claim_embeddings_observation_ref_non_empty
        CHECK (length(trim(observation_ref)) > 0),

    CONSTRAINT chk_draft_claim_embeddings_text_non_empty
        CHECK (length(trim(embedding_text)) > 0),

    CONSTRAINT chk_draft_claim_embeddings_text_hash_non_empty
        CHECK (length(trim(embedding_text_hash)) > 0),

    CONSTRAINT chk_draft_claim_embeddings_model_non_empty
        CHECK (length(trim(embedding_model_id)) > 0),

    CONSTRAINT chk_draft_claim_embeddings_dimensions_384
        CHECK (dimensions = 384),

    CONSTRAINT uq_draft_claim_embeddings_observation_model_text
        UNIQUE (observation_ref, embedding_model_id, embedding_text_hash)
);

CREATE INDEX IF NOT EXISTS idx_draft_claim_embeddings_workflow_run
    ON draft_claim_embeddings (workflow_run_id, created_at);

CREATE INDEX IF NOT EXISTS idx_draft_claim_embeddings_source_document
    ON draft_claim_embeddings (source_document_ref, created_at);

CREATE INDEX IF NOT EXISTS idx_draft_claim_embeddings_source_unit
    ON draft_claim_embeddings (source_unit_ref, created_at);

CREATE INDEX IF NOT EXISTS idx_draft_claim_embeddings_observation
    ON draft_claim_embeddings (observation_ref);

CREATE INDEX IF NOT EXISTS idx_draft_claim_embeddings_vector_ivfflat
    ON draft_claim_embeddings USING ivfflat (embedding vector_cosine_ops);
