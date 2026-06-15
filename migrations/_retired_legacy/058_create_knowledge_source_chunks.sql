-- Migration 058: Persist raw SourceChunk records for KCD v1 Stage B.
--
-- Runtime retrieval intentionally remains on knowledge_base in this stage.
-- This table stores extracted source material separately so later stages can
-- link CanonicalKnowledgeEntry rows to exact source evidence.

BEGIN;

CREATE TABLE IF NOT EXISTS knowledge_source_chunks (
    id TEXT PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    source_index INTEGER NOT NULL,
    content TEXT NOT NULL,
    page INTEGER,
    section_title TEXT NOT NULL DEFAULT '',
    start_offset INTEGER,
    end_offset INTEGER,
    checksum TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_knowledge_source_chunks_source_index
        CHECK (source_index >= 0),
    CONSTRAINT ck_knowledge_source_chunks_content_not_blank
        CHECK (btrim(content) <> ''),
    CONSTRAINT ck_knowledge_source_chunks_offsets
        CHECK (
            start_offset IS NULL
            OR end_offset IS NULL
            OR end_offset >= start_offset
        ),
    CONSTRAINT uq_knowledge_source_chunks_document_index
        UNIQUE (document_id, source_index)
);

CREATE INDEX IF NOT EXISTS idx_knowledge_source_chunks_project_document
    ON knowledge_source_chunks(project_id, document_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_source_chunks_document_index
    ON knowledge_source_chunks(document_id, source_index);

CREATE INDEX IF NOT EXISTS idx_knowledge_source_chunks_project_created_at
    ON knowledge_source_chunks(project_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_knowledge_source_chunks_checksum
    ON knowledge_source_chunks(checksum)
    WHERE checksum <> '';

ANALYZE knowledge_source_chunks;

COMMIT;
