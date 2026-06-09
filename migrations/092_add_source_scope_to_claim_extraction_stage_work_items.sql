ALTER TABLE claim_extraction_stage_work_items
    ADD COLUMN IF NOT EXISTS source_document_ref text,
    ADD COLUMN IF NOT EXISTS source_unit_ref text;

UPDATE claim_extraction_stage_work_items
SET source_document_ref = workflow_run_id,
    source_unit_ref = work_item_id
WHERE source_document_ref IS NULL
   OR source_unit_ref IS NULL;

ALTER TABLE claim_extraction_stage_work_items
    ALTER COLUMN source_document_ref SET NOT NULL,
    ALTER COLUMN source_unit_ref SET NOT NULL;
