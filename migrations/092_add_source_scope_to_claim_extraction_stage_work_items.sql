ALTER TABLE claim_extraction_stage_work_items ADD COLUMN IF NOT EXISTS source_document_ref text NOT NULL;
ALTER TABLE claim_extraction_stage_work_items ADD COLUMN IF NOT EXISTS source_unit_ref text NOT NULL;
