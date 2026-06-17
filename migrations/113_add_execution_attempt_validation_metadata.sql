ALTER TABLE execution_work_item_attempts
    ADD COLUMN IF NOT EXISTS validation_metadata JSONB;
