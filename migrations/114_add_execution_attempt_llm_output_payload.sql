ALTER TABLE execution_work_item_attempts
    ADD COLUMN IF NOT EXISTS llm_output_payload JSONB;
