-- Migration 059: KCD v1 Stage C+D canonical entries and retrieval surface.
--
-- Target architecture:
-- - CanonicalKnowledgeEntry is persisted in knowledge_entries.
-- - Source evidence is persisted in knowledge_entry_source_refs and links to knowledge_source_chunks.
-- - Runtime retrieval reads knowledge_retrieval_surface, not legacy knowledge_base.
-- - knowledge_base is intentionally not renamed and not used as the target model.

BEGIN;

CREATE TABLE IF NOT EXISTS knowledge_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    compiler_run_id TEXT,
    stable_key TEXT NOT NULL,
    entry_kind TEXT NOT NULL,
    title TEXT NOT NULL,
    answer TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    visibility TEXT NOT NULL DEFAULT 'owner_only',
    version INTEGER NOT NULL DEFAULT 1,
    compiler_version TEXT NOT NULL DEFAULT '',
    embedding_text TEXT NOT NULL DEFAULT '',
    embedding_text_version TEXT NOT NULL DEFAULT '',
    enrichment JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_knowledge_entries_stable_key_not_blank CHECK (btrim(stable_key) <> ''),
    CONSTRAINT ck_knowledge_entries_title_not_blank CHECK (btrim(title) <> ''),
    CONSTRAINT ck_knowledge_entries_answer_not_blank CHECK (btrim(answer) <> ''),
    CONSTRAINT ck_knowledge_entries_version_positive CHECK (version >= 1),
    CONSTRAINT ck_knowledge_entries_status CHECK (
        status IN (
            'draft',
            'grounded',
            'enriched',
            'embedded',
            'published',
            'needs_review',
            'hidden',
            'archived',
            'rejected'
        )
    ),
    CONSTRAINT ck_knowledge_entries_visibility CHECK (
        visibility IN ('runtime', 'owner_only', 'internal', 'hidden')
    ),
    CONSTRAINT ck_knowledge_entries_entry_kind CHECK (
        entry_kind IN (
            'answer',
            'faq_answer',
            'contact_info',
            'working_hours',
            'catalog_answer',
            'price_answer',
            'pricing_policy',
            'refund_policy',
            'delivery_policy',
            'policy_clause',
            'procedure',
            'warning',
            'requirement',
            'troubleshooting_step',
            'fallback_chunk',
            'custom'
        )
    ),
    CONSTRAINT uq_knowledge_entries_project_document_stable_version
        UNIQUE (project_id, document_id, stable_key, version)
);

CREATE TABLE IF NOT EXISTS knowledge_entry_source_refs (
    entry_id UUID NOT NULL REFERENCES knowledge_entries(id) ON DELETE CASCADE,
    source_chunk_id TEXT NOT NULL REFERENCES knowledge_source_chunks(id) ON DELETE CASCADE,
    source_index INTEGER NOT NULL,
    quote TEXT NOT NULL DEFAULT '',
    start_offset INTEGER,
    end_offset INTEGER,
    confidence DOUBLE PRECISION,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT pk_knowledge_entry_source_refs
        PRIMARY KEY (entry_id, source_chunk_id, source_index),
    CONSTRAINT ck_knowledge_entry_source_refs_source_index
        CHECK (source_index >= 0),
    CONSTRAINT ck_knowledge_entry_source_refs_offsets
        CHECK (
            start_offset IS NULL
            OR end_offset IS NULL
            OR end_offset >= start_offset
        ),
    CONSTRAINT ck_knowledge_entry_source_refs_confidence
        CHECK (
            confidence IS NULL
            OR (confidence >= 0.0 AND confidence <= 1.0)
        )
);

CREATE TABLE IF NOT EXISTS knowledge_retrieval_surface (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    document_id UUID REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    entry_id UUID NOT NULL REFERENCES knowledge_entries(id) ON DELETE CASCADE,
    stable_key TEXT NOT NULL,
    entry_kind TEXT NOT NULL,
    title TEXT NOT NULL,
    answer TEXT NOT NULL,
    embedding_text TEXT NOT NULL,
    embedding_text_version TEXT NOT NULL DEFAULT '',
    embedding vector(384),
    search_text TEXT NOT NULL,
    enrichment JSONB NOT NULL DEFAULT '{}'::jsonb,
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    status TEXT NOT NULL DEFAULT 'published',
    visibility TEXT NOT NULL DEFAULT 'runtime',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_knowledge_retrieval_surface_entry
        UNIQUE (entry_id),
    CONSTRAINT ck_knowledge_retrieval_surface_runtime_status
        CHECK (status = 'published'),
    CONSTRAINT ck_knowledge_retrieval_surface_runtime_visibility
        CHECK (visibility = 'runtime'),
    CONSTRAINT ck_knowledge_retrieval_surface_answer_not_blank
        CHECK (btrim(answer) <> ''),
    CONSTRAINT ck_knowledge_retrieval_surface_embedding_text_not_blank
        CHECK (btrim(embedding_text) <> '')
);

CREATE INDEX IF NOT EXISTS idx_knowledge_entries_project_document
    ON knowledge_entries(project_id, document_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_entries_project_status_visibility
    ON knowledge_entries(project_id, status, visibility);

CREATE INDEX IF NOT EXISTS idx_knowledge_entries_document_kind
    ON knowledge_entries(document_id, entry_kind);

CREATE INDEX IF NOT EXISTS idx_knowledge_entry_source_refs_source_chunk
    ON knowledge_entry_source_refs(source_chunk_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_retrieval_surface_project_document
    ON knowledge_retrieval_surface(project_id, document_id);

CREATE INDEX IF NOT EXISTS idx_knowledge_retrieval_surface_project_kind
    ON knowledge_retrieval_surface(project_id, entry_kind);

CREATE INDEX IF NOT EXISTS idx_knowledge_retrieval_surface_embedding_ivfflat
    ON knowledge_retrieval_surface USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_knowledge_retrieval_surface_search_text_fts
    ON knowledge_retrieval_surface
    USING gin (to_tsvector('russian', search_text));

ANALYZE knowledge_entries;
ANALYZE knowledge_entry_source_refs;
ANALYZE knowledge_retrieval_surface;

COMMIT;
