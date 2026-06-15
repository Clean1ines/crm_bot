-- Allow knowledge edit actions to use the in-progress lifecycle state.
--
-- Manual curation merge marks an action as in_progress while the merge mutation
-- and follow-up finalization are running. Production rejected that state through
-- ck_knowledge_edit_actions_status, causing /curation/merge/apply to fail with
-- HTTP 500.

BEGIN;

ALTER TABLE knowledge_edit_actions
    DROP CONSTRAINT IF EXISTS ck_knowledge_edit_actions_status;

ALTER TABLE knowledge_edit_actions
    ADD CONSTRAINT ck_knowledge_edit_actions_status
    CHECK (
        status IN (
            'proposed',
            'in_progress',
            'applied',
            'applied_with_warning',
            'rejected',
            'failed'
        )
    );

COMMIT;
