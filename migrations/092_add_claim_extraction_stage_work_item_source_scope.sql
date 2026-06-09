-- Add source ownership scope to claim extraction stage work item index.
-- This keeps Execution Runtime generic while making Workbench extraction work
-- traceable to source documents and source units.

ALTER TABLE claim_extraction_stage_work_items
    ADD COLUMN IF NOT EXISTS source_document_ref text;

ALTER TABLE claim_extraction_stage_work_items
    ADD COLUMN IF NOT EXISTS source_unit_ref text;

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM claim_extraction_stage_work_items
        WHERE source_document_ref IS NULL
           OR source_unit_ref IS NULL
    ) THEN
        RAISE EXCEPTION 'claim_extraction_stage_work_items has rows without source scope; manual backfill required before enforcing NOT NULL';
    END IF;
END $$;

ALTER TABLE claim_extraction_stage_work_items
    ALTER COLUMN source_document_ref SET NOT NULL;

ALTER TABLE claim_extraction_stage_work_items
    ALTER COLUMN source_unit_ref SET NOT NULL;
