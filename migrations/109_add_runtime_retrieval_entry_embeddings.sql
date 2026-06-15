-- Runtime vector embeddings for published Workbench retrieval entries.
-- Draft Prompt A embeddings remain temporary clustering artifacts and are deleted
-- after successful curated runtime publication.

CREATE TABLE IF NOT EXISTS knowledge_workbench_runtime_retrieval_entry_embeddings (
    runtime_entry_id TEXT NOT NULL REFERENCES knowledge_workbench_runtime_retrieval_entries(runtime_entry_id) ON DELETE CASCADE,
    embedding_model_id TEXT NOT NULL,
    dimensions INTEGER NOT NULL,
    embedding vector(384) NOT NULL,
    embedding_text_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (runtime_entry_id, embedding_model_id, embedding_text_hash),

    CONSTRAINT chk_kwb_runtime_entry_embeddings_model_non_empty
        CHECK (length(trim(embedding_model_id)) > 0),
    CONSTRAINT chk_kwb_runtime_entry_embeddings_dimensions_384
        CHECK (dimensions = 384),
    CONSTRAINT chk_kwb_runtime_entry_embeddings_hash_non_empty
        CHECK (length(trim(embedding_text_hash)) > 0)
);

CREATE INDEX IF NOT EXISTS idx_kwb_runtime_entry_embeddings_vector_ivfflat
    ON knowledge_workbench_runtime_retrieval_entry_embeddings
    USING ivfflat (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_kwb_runtime_entry_embeddings_model
    ON knowledge_workbench_runtime_retrieval_entry_embeddings(runtime_entry_id, embedding_model_id);
