-- Fix retry_plan DB constraint without modifying already-applied migrations.
-- Runtime persists WorkItemRetryPlan values from the current enum.

ALTER TABLE execution_work_items
    DROP CONSTRAINT IF EXISTS chk_execution_work_items_retry_plan;

UPDATE execution_work_items
SET retry_plan = CASE retry_plan
    WHEN 'retry_same_model' THEN 'retry_same_route'
    WHEN 'retry_other_org' THEN 'retry_alternate_route'
    WHEN 'retry_special_empty_claims_check_model' THEN 'retry_validation_check_route'
    WHEN 'retry_larger_context_model' THEN 'retry_larger_input_limit_route'
    WHEN 'retry_larger_output_model' THEN 'retry_larger_output_limit_route'
    WHEN 'retry_daily_fallback_model' THEN 'retry_daily_fallback_route'
    WHEN 'wait_nearest_capacity_window' THEN 'wait_nearest_admission_window'
    WHEN 'split_source_unit' THEN 'split_work_payload'
    WHEN 'wait_daily_capacity_reset' THEN 'wait_daily_admission_reset'
    ELSE retry_plan
END
WHERE retry_plan IN (
    'retry_same_model',
    'retry_other_org',
    'retry_special_empty_claims_check_model',
    'retry_larger_context_model',
    'retry_larger_output_model',
    'retry_daily_fallback_model',
    'wait_nearest_capacity_window',
    'split_source_unit',
    'wait_daily_capacity_reset'
);

ALTER TABLE execution_work_items
    ADD CONSTRAINT chk_execution_work_items_retry_plan
    CHECK (
        retry_plan IS NULL
        OR retry_plan IN (
            'retry_same_route',
            'retry_alternate_route',
            'retry_validation_check_route',
            'retry_larger_input_limit_route',
            'retry_larger_output_limit_route',
            'retry_daily_fallback_route',
            'wait_nearest_admission_window',
            'split_work_payload',
            'wait_daily_admission_reset',
            'terminal'
        )
    );
