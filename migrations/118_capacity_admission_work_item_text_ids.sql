-- Align Capacity Admission Queue projection identifiers with Workflow Runtime.
--
-- knowledge_extraction_workflow_runs.workflow_run_id and project_id are text
-- identifiers, not UUIDs. The admission projection is not the lifecycle source
-- of truth, so it must mirror those identifiers without narrowing their type.

ALTER TABLE capacity_admission_work_items
    ALTER COLUMN workflow_run_id TYPE TEXT USING workflow_run_id::text,
    ALTER COLUMN project_id TYPE TEXT USING project_id::text;
