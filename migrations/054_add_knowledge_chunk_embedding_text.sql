-- Adds retrieval-optimized embedding text to the actual KB chunk table.
-- Current project schema stores chunks in knowledge_base, not knowledge_chunks.

ALTER TABLE knowledge_base
ADD COLUMN IF NOT EXISTS embedding_text TEXT;

CREATE INDEX IF NOT EXISTS idx_knowledge_base_project_embedding_text_not_null
ON knowledge_base (project_id)
WHERE embedding_text IS NOT NULL;
