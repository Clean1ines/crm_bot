-- Drop retired legacy knowledge/RAG/artifact schema residue.
--
-- Fresh DB:
--   legacy create migrations are no longer active, so these objects should not exist.
--
-- Existing DB:
--   older filename-based migrations may already have created them; this migration
--   removes the retired tables idempotently.

BEGIN;

-- Old RAG eval review/action layer.
DROP TABLE IF EXISTS rag_eval_review_items CASCADE;
DROP TABLE IF EXISTS rag_eval_question_reviews CASCADE;
DROP TABLE IF EXISTS rag_eval_review_groups CASCADE;
DROP TABLE IF EXISTS rag_eval_failure_actions CASCADE;
DROP TABLE IF EXISTS rag_quality_reports CASCADE;
DROP TABLE IF EXISTS rag_eval_results CASCADE;
DROP TABLE IF EXISTS rag_eval_runs CASCADE;
DROP TABLE IF EXISTS rag_eval_jobs CASCADE;
DROP TABLE IF EXISTS rag_eval_questions CASCADE;
DROP TABLE IF EXISTS rag_eval_datasets CASCADE;

-- Old KCD entry/retrieval/edit layer.
DROP TABLE IF EXISTS knowledge_entry_versions CASCADE;
DROP TABLE IF EXISTS knowledge_edit_actions CASCADE;
DROP TABLE IF EXISTS knowledge_entry_source_refs CASCADE;
DROP TABLE IF EXISTS knowledge_retrieval_surface CASCADE;
DROP TABLE IF EXISTS knowledge_entries CASCADE;
DROP TABLE IF EXISTS knowledge_source_chunks CASCADE;

-- Old Workbench surface-card/proposal layer.
DROP TABLE IF EXISTS knowledge_workbench_surface_cards CASCADE;
DROP TABLE IF EXISTS knowledge_workbench_surfaces CASCADE;

-- Retired Artifact Runtime prototype.
DROP TABLE IF EXISTS pipeline_artifact_lineage CASCADE;
DROP TABLE IF EXISTS pipeline_artifacts CASCADE;

-- Defensive index cleanup for already-mutated DBs. DROP TABLE removes table-owned
-- indexes, but these names may exist as residue after partial migrations.
DROP INDEX IF EXISTS idx_knowledge_source_chunks_project_document;
DROP INDEX IF EXISTS idx_knowledge_source_chunks_document_index;
DROP INDEX IF EXISTS idx_knowledge_source_chunks_project_created_at;
DROP INDEX IF EXISTS idx_knowledge_source_chunks_checksum;
DROP INDEX IF EXISTS idx_knowledge_entries_project_document;
DROP INDEX IF EXISTS idx_knowledge_entries_project_status_visibility;
DROP INDEX IF EXISTS idx_knowledge_entries_document_kind;
DROP INDEX IF EXISTS idx_knowledge_entry_source_refs_source_chunk;
DROP INDEX IF EXISTS idx_knowledge_retrieval_surface_project_document;
DROP INDEX IF EXISTS idx_knowledge_retrieval_surface_project_kind;
DROP INDEX IF EXISTS idx_knowledge_retrieval_surface_embedding_ivfflat;
DROP INDEX IF EXISTS idx_knowledge_retrieval_surface_search_text_fts;
DROP INDEX IF EXISTS idx_knowledge_edit_actions_project_document;
DROP INDEX IF EXISTS idx_knowledge_edit_actions_target_entry;
DROP INDEX IF EXISTS idx_knowledge_edit_actions_status;
DROP INDEX IF EXISTS idx_knowledge_entry_versions_entry_created;
DROP INDEX IF EXISTS idx_knowledge_entry_versions_action;
DROP INDEX IF EXISTS idx_rag_eval_datasets_project_document;
DROP INDEX IF EXISTS idx_rag_eval_questions_dataset;
DROP INDEX IF EXISTS idx_rag_eval_questions_project_document;
DROP INDEX IF EXISTS idx_rag_eval_questions_type;
DROP INDEX IF EXISTS idx_rag_eval_runs_dataset_started;
DROP INDEX IF EXISTS idx_rag_eval_runs_project_document;
DROP INDEX IF EXISTS idx_rag_eval_results_run;
DROP INDEX IF EXISTS idx_rag_eval_results_question;
DROP INDEX IF EXISTS idx_rag_eval_results_failed;
DROP INDEX IF EXISTS idx_rag_quality_reports_project_document;
DROP INDEX IF EXISTS idx_rag_eval_question_reviews_run_status;
DROP INDEX IF EXISTS idx_rag_eval_question_reviews_document;
DROP INDEX IF EXISTS idx_rag_eval_review_groups_run_status;
DROP INDEX IF EXISTS idx_rag_eval_review_groups_document;

COMMIT;
