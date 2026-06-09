ALTER TABLE claim_extraction_stage_work_items ADD CONSTRAINT chk_claim_extraction_stage_work_items_source_document_non_empty CHECK (length(trim(source_document_ref)) > 0);
ALTER TABLE claim_extraction_stage_work_items ADD CONSTRAINT chk_claim_extraction_stage_work_items_source_unit_non_empty CHECK (length(trim(source_unit_ref)) > 0);
