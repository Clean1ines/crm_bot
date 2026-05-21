-- Migration 066: Commercial Price Knowledge persistence.
--
-- Commercial Price Knowledge is intentionally separate from generic RAG storage.
-- Generic knowledge_entries may still explain pricing policy, but concrete prices,
-- variants, price ranges, and "on request" commercial facts must have their own
-- source-grounded lifecycle and runtime lookup path.

BEGIN;

CREATE TABLE IF NOT EXISTS commercial_price_documents (
    id TEXT PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    knowledge_document_id UUID NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    source_format TEXT NOT NULL DEFAULT 'unknown',
    input_kind TEXT NOT NULL DEFAULT 'unknown',
    status TEXT NOT NULL DEFAULT 'draft',
    detected_currency TEXT,
    detected_locale TEXT,
    error TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_commercial_price_documents_knowledge_document
        UNIQUE (project_id, knowledge_document_id),

    CONSTRAINT uq_commercial_price_documents_id_project
        UNIQUE (id, project_id),

    CONSTRAINT ck_commercial_price_documents_id_not_blank
        CHECK (btrim(id) <> ''),

    CONSTRAINT ck_commercial_price_documents_source_format CHECK (
        source_format IN (
            'markdown',
            'plain_text',
            'csv',
            'xlsx',
            'pdf_text',
            'pdf_table',
            'unknown'
        )
    ),

    CONSTRAINT ck_commercial_price_documents_input_kind CHECK (
        input_kind IN (
            'table',
            'structured_text',
            'unstructured_text',
            'mixed',
            'unknown'
        )
    ),

    CONSTRAINT ck_commercial_price_documents_status CHECK (
        status IN (
            'draft',
            'processing',
            'needs_review',
            'ready',
            'failed'
        )
    ),

    CONSTRAINT ck_commercial_price_documents_detected_currency_not_blank CHECK (
        detected_currency IS NULL OR btrim(detected_currency) <> ''
    ),

    CONSTRAINT ck_commercial_price_documents_detected_locale_not_blank CHECK (
        detected_locale IS NULL OR btrim(detected_locale) <> ''
    ),

    CONSTRAINT ck_commercial_price_documents_metadata_object CHECK (
        jsonb_typeof(metadata) = 'object'
    )
);

CREATE TABLE IF NOT EXISTS commercial_price_source_units (
    id TEXT PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    price_document_id TEXT NOT NULL REFERENCES commercial_price_documents(id) ON DELETE CASCADE,
    source_index INTEGER NOT NULL,
    kind TEXT NOT NULL DEFAULT 'unknown',
    raw_text TEXT NOT NULL,
    title TEXT NOT NULL DEFAULT '',
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_commercial_price_source_units_document_index
        UNIQUE (price_document_id, source_index),

    CONSTRAINT uq_commercial_price_source_units_id_document_project
        UNIQUE (id, price_document_id, project_id),

    CONSTRAINT fk_commercial_price_source_units_document_project
        FOREIGN KEY (price_document_id, project_id)
        REFERENCES commercial_price_documents(id, project_id)
        ON DELETE CASCADE,

    CONSTRAINT ck_commercial_price_source_units_id_not_blank
        CHECK (btrim(id) <> ''),

    CONSTRAINT ck_commercial_price_source_units_source_index
        CHECK (source_index >= 0),

    CONSTRAINT ck_commercial_price_source_units_kind CHECK (
        kind IN (
            'table',
            'structured_text',
            'unstructured_text',
            'mixed',
            'unknown'
        )
    ),

    CONSTRAINT ck_commercial_price_source_units_raw_text_not_blank
        CHECK (btrim(raw_text) <> ''),

    CONSTRAINT ck_commercial_price_source_units_metadata_object CHECK (
        jsonb_typeof(metadata) = 'object'
    )
);

CREATE TABLE IF NOT EXISTS commercial_price_source_rows (
    id TEXT PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    price_document_id TEXT NOT NULL REFERENCES commercial_price_documents(id) ON DELETE CASCADE,
    source_unit_id TEXT NOT NULL REFERENCES commercial_price_source_units(id) ON DELETE CASCADE,
    row_index INTEGER NOT NULL,
    raw_cells JSONB NOT NULL,
    normalized_cells JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_commercial_price_source_rows_unit_index
        UNIQUE (source_unit_id, row_index),

    CONSTRAINT fk_commercial_price_source_rows_unit_document_project
        FOREIGN KEY (source_unit_id, price_document_id, project_id)
        REFERENCES commercial_price_source_units(id, price_document_id, project_id)
        ON DELETE CASCADE,

    CONSTRAINT ck_commercial_price_source_rows_id_not_blank
        CHECK (btrim(id) <> ''),

    CONSTRAINT ck_commercial_price_source_rows_index
        CHECK (row_index >= 0),

    CONSTRAINT ck_commercial_price_source_rows_raw_cells_object
        CHECK (jsonb_typeof(raw_cells) = 'object'),

    CONSTRAINT ck_commercial_price_source_rows_raw_cells_not_empty
        CHECK (raw_cells <> '{}'::jsonb),

    CONSTRAINT ck_commercial_price_source_rows_normalized_cells_object
        CHECK (jsonb_typeof(normalized_cells) = 'object')
);

CREATE TABLE IF NOT EXISTS commercial_price_facts (
    id TEXT PRIMARY KEY,
    project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
    price_document_id TEXT NOT NULL REFERENCES commercial_price_documents(id) ON DELETE CASCADE,
    item_name TEXT NOT NULL,
    value_kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'draft',
    amount NUMERIC(18, 6),
    min_amount NUMERIC(18, 6),
    max_amount NUMERIC(18, 6),
    currency TEXT,
    unit TEXT NOT NULL,
    price_text TEXT NOT NULL DEFAULT '',
    variant JSONB NOT NULL DEFAULT '{}'::jsonb,
    aliases JSONB NOT NULL DEFAULT '[]'::jsonb,
    conditions JSONB NOT NULL DEFAULT '[]'::jsonb,
    source_refs JSONB NOT NULL DEFAULT '[]'::jsonb,
    confidence DOUBLE PRECISION NOT NULL DEFAULT 0.0,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT fk_commercial_price_facts_document_project
        FOREIGN KEY (price_document_id, project_id)
        REFERENCES commercial_price_documents(id, project_id)
        ON DELETE CASCADE,

    CONSTRAINT ck_commercial_price_facts_id_not_blank
        CHECK (btrim(id) <> ''),

    CONSTRAINT ck_commercial_price_facts_item_name_not_blank
        CHECK (btrim(item_name) <> ''),

    CONSTRAINT ck_commercial_price_facts_unit_not_blank
        CHECK (btrim(unit) <> ''),

    CONSTRAINT ck_commercial_price_facts_value_kind CHECK (
        value_kind IN (
            'exact',
            'starting_from',
            'range',
            'on_request'
        )
    ),

    CONSTRAINT ck_commercial_price_facts_status CHECK (
        status IN (
            'draft',
            'needs_review',
            'published',
            'rejected',
            'superseded'
        )
    ),

    CONSTRAINT ck_commercial_price_facts_confidence CHECK (
        confidence >= 0.0 AND confidence <= 1.0
    ),

    CONSTRAINT ck_commercial_price_facts_variant_object CHECK (
        jsonb_typeof(variant) = 'object'
    ),

    CONSTRAINT ck_commercial_price_facts_aliases_array CHECK (
        jsonb_typeof(aliases) = 'array'
    ),

    CONSTRAINT ck_commercial_price_facts_conditions_array CHECK (
        jsonb_typeof(conditions) = 'array'
    ),

    CONSTRAINT ck_commercial_price_facts_source_refs_array CHECK (
        jsonb_typeof(source_refs) = 'array'
    ),

    CONSTRAINT ck_commercial_price_facts_source_refs_not_empty CHECK (
        jsonb_array_length(source_refs) > 0
    ),

    CONSTRAINT ck_commercial_price_facts_metadata_object CHECK (
        jsonb_typeof(metadata) = 'object'
    ),

    CONSTRAINT ck_commercial_price_facts_non_negative_amounts CHECK (
        (amount IS NULL OR amount >= 0)
        AND (min_amount IS NULL OR min_amount >= 0)
        AND (max_amount IS NULL OR max_amount >= 0)
    ),

    CONSTRAINT ck_commercial_price_facts_range_order CHECK (
        min_amount IS NULL
        OR max_amount IS NULL
        OR min_amount <= max_amount
    ),

    CONSTRAINT ck_commercial_price_facts_currency_not_blank CHECK (
        currency IS NULL OR btrim(currency) <> ''
    ),

    CONSTRAINT ck_commercial_price_facts_exact_shape CHECK (
        value_kind NOT IN ('exact', 'starting_from')
        OR (
            amount IS NOT NULL
            AND currency IS NOT NULL
            AND btrim(currency) <> ''
            AND min_amount IS NULL
            AND max_amount IS NULL
        )
    ),

    CONSTRAINT ck_commercial_price_facts_range_shape CHECK (
        value_kind <> 'range'
        OR (
            amount IS NULL
            AND min_amount IS NOT NULL
            AND max_amount IS NOT NULL
            AND currency IS NOT NULL
            AND btrim(currency) <> ''
        )
    ),

    CONSTRAINT ck_commercial_price_facts_on_request_shape CHECK (
        value_kind <> 'on_request'
        OR (
            amount IS NULL
            AND min_amount IS NULL
            AND max_amount IS NULL
            AND currency IS NULL
            AND btrim(price_text) <> ''
        )
    )
);

CREATE INDEX IF NOT EXISTS idx_commercial_price_documents_project_status
    ON commercial_price_documents(project_id, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS idx_commercial_price_documents_knowledge_document
    ON commercial_price_documents(knowledge_document_id);

CREATE INDEX IF NOT EXISTS idx_commercial_price_source_units_document_index
    ON commercial_price_source_units(price_document_id, source_index);

CREATE INDEX IF NOT EXISTS idx_commercial_price_source_units_project_document
    ON commercial_price_source_units(project_id, price_document_id);

CREATE INDEX IF NOT EXISTS idx_commercial_price_source_rows_document_unit
    ON commercial_price_source_rows(price_document_id, source_unit_id, row_index);

CREATE INDEX IF NOT EXISTS idx_commercial_price_facts_project_document_status
    ON commercial_price_facts(project_id, price_document_id, status);

CREATE INDEX IF NOT EXISTS idx_commercial_price_facts_runtime_lookup
    ON commercial_price_facts(project_id, lower(item_name), status)
    WHERE status = 'published';

CREATE INDEX IF NOT EXISTS idx_commercial_price_facts_variant_gin
    ON commercial_price_facts USING gin (variant);

CREATE INDEX IF NOT EXISTS idx_commercial_price_facts_aliases_gin
    ON commercial_price_facts USING gin (aliases);

COMMENT ON TABLE commercial_price_documents IS
    'Commercial Price Knowledge v1 source documents derived from uploaded knowledge documents with preprocessing_mode=price_list.';

COMMENT ON TABLE commercial_price_source_units IS
    'Commercial Price Knowledge v1 source units: extracted table/text units used as evidence for price facts.';

COMMENT ON TABLE commercial_price_source_rows IS
    'Commercial Price Knowledge v1 normalized table rows when a price source unit is tabular.';

COMMENT ON TABLE commercial_price_facts IS
    'Commercial Price Knowledge v1 grounded price facts used by priority structured price lookup before generic RAG.';

ANALYZE commercial_price_documents;
ANALYZE commercial_price_source_units;
ANALYZE commercial_price_source_rows;
ANALYZE commercial_price_facts;

COMMIT;
