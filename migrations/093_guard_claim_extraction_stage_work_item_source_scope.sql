-- Guard source ownership scope for claim extraction stage work item index.

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_claim_extraction_stage_work_items_source_document_non_empty'
          AND conrelid = 'claim_extraction_stage_work_items'::regclass
    ) THEN
        ALTER TABLE claim_extraction_stage_work_items
            ADD CONSTRAINT chk_claim_extraction_stage_work_items_source_document_non_empty
            CHECK (length(trim(source_document_ref)) > 0);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'chk_claim_extraction_stage_work_items_source_unit_non_empty'
          AND conrelid = 'claim_extraction_stage_work_items'::regclass
    ) THEN
        ALTER TABLE claim_extraction_stage_work_items
            ADD CONSTRAINT chk_claim_extraction_stage_work_items_source_unit_non_empty
            CHECK (length(trim(source_unit_ref)) > 0);
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_claim_extraction_stage_work_items_source_document'
          AND conrelid = 'claim_extraction_stage_work_items'::regclass
    ) THEN
        ALTER TABLE claim_extraction_stage_work_items
            ADD CONSTRAINT fk_claim_extraction_stage_work_items_source_document
            FOREIGN KEY (source_document_ref)
            REFERENCES source_documents(document_ref)
            ON DELETE CASCADE;
    END IF;
END $$;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'fk_claim_extraction_stage_work_items_source_unit'
          AND conrelid = 'claim_extraction_stage_work_items'::regclass
    ) THEN
        ALTER TABLE claim_extraction_stage_work_items
            ADD CONSTRAINT fk_claim_extraction_stage_work_items_source_unit
            FOREIGN KEY (source_unit_ref)
            REFERENCES source_units(unit_ref)
            ON DELETE CASCADE;
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_claim_extraction_stage_work_items_document
    ON claim_extraction_stage_work_items (workflow_run_id, source_document_ref, created_at);

CREATE INDEX IF NOT EXISTS idx_claim_extraction_stage_work_items_source_unit
    ON claim_extraction_stage_work_items (workflow_run_id, source_document_ref, source_unit_ref);

CREATE UNIQUE INDEX IF NOT EXISTS uq_claim_extraction_stage_work_items_stage_source_unit
    ON claim_extraction_stage_work_items (workflow_run_id, stage_run_id, source_unit_ref);
