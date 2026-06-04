-- D4C6-real-15a
-- Intentionally no-op after destructive empty-DB cutover.
--
-- Retention columns for fact registries, registry snapshots, and canonical facts
-- are created directly in 070_create_faq_workbench_v1.sql.
--
-- Old question-registry retention migration was removed because the Workbench
-- registry model is now fact-registry based.
--
-- Keep this as executable SQL because asyncpg.execute() may fail on a
-- comment-only migration body.

DO $$
BEGIN
    NULL;
END $$;
