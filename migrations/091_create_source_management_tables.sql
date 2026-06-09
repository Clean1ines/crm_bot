-- Canonical Source Management durable persistence.
-- These rows belong to Knowledge Workbench Source Management, not old FAQ/Workbench tables.

CREATE TABLE IF NOT EXISTS source_documents (
    document_ref text PRIMARY KEY,
    project_id text NOT NULL,
    source_format text NOT NULL,
    content_hash text NOT NULL,
    original_filename text NULL,
    created_at timestamptz NOT NULL,

    CONSTRAINT chk_source_documents_ref_non_empty
        CHECK (btrim(document_ref) <> ''),

    CONSTRAINT chk_source_documents_project_non_empty
        CHECK (btrim(project_id) <> ''),

    CONSTRAINT chk_source_documents_format_non_empty
        CHECK (btrim(source_format) <> ''),

    CONSTRAINT chk_source_documents_content_hash_non_empty
        CHECK (btrim(content_hash) <> ''),

    CONSTRAINT chk_source_documents_original_filename_non_empty
        CHECK (original_filename IS NULL OR btrim(original_filename) <> '')
);

CREATE INDEX IF NOT EXISTS idx_source_documents_project
    ON source_documents (project_id);

CREATE INDEX IF NOT EXISTS idx_source_documents_content_hash
    ON source_documents (content_hash);

CREATE INDEX IF NOT EXISTS idx_source_documents_created_at
    ON source_documents (created_at);

CREATE TABLE IF NOT EXISTS source_units (
    unit_ref text PRIMARY KEY,
    document_ref text NOT NULL REFERENCES source_documents(document_ref) ON DELETE CASCADE,
    unit_kind text NOT NULL,
    text text NOT NULL,
    heading_path jsonb NOT NULL DEFAULT '[]'::jsonb,
    lineage jsonb NOT NULL DEFAULT '{}'::jsonb,
    ordinal integer NOT NULL,
    created_at timestamptz NOT NULL,

    CONSTRAINT chk_source_units_ref_non_empty
        CHECK (btrim(unit_ref) <> ''),

    CONSTRAINT chk_source_units_document_ref_non_empty
        CHECK (btrim(document_ref) <> ''),

    CONSTRAINT chk_source_units_kind_non_empty
        CHECK (btrim(unit_kind) <> ''),

    CONSTRAINT chk_source_units_text_non_empty
        CHECK (btrim(text) <> ''),

    CONSTRAINT chk_source_units_heading_path_is_array
        CHECK (jsonb_typeof(heading_path) = 'array'),

    CONSTRAINT chk_source_units_lineage_is_object
        CHECK (jsonb_typeof(lineage) = 'object'),

    CONSTRAINT chk_source_units_ordinal_non_negative
        CHECK (ordinal >= 0),

    CONSTRAINT uq_source_units_document_ordinal
        UNIQUE (document_ref, ordinal)
);

CREATE INDEX IF NOT EXISTS idx_source_units_document
    ON source_units (document_ref);

CREATE INDEX IF NOT EXISTS idx_source_units_document_ordinal
    ON source_units (document_ref, ordinal);

CREATE INDEX IF NOT EXISTS idx_source_units_kind
    ON source_units (unit_kind);

CREATE INDEX IF NOT EXISTS idx_source_units_created_at
    ON source_units (created_at);
