from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "migrations"

EXPECTED_MIGRATIONS = {
    "083_create_execution_runtime_tables.sql": (
        "CREATE TABLE IF NOT EXISTS execution_work_items",
        "CREATE TABLE IF NOT EXISTS execution_work_item_attempts",
        "idx_execution_work_items_ready_due",
        "idx_execution_work_items_lease_expiry",
        "idx_execution_work_items_user_action",
        "idx_execution_work_item_attempts_work_item",
    ),
    "084_create_llm_runtime_tables.sql": (
        "CREATE TABLE IF NOT EXISTS llm_tasks",
        "CREATE TABLE IF NOT EXISTS llm_attempts",
        "idx_llm_tasks_status_wait",
        "idx_llm_tasks_prompt_input",
        "idx_llm_attempts_task",
    ),
    "085_create_artifact_runtime_tables.sql": (
        "CREATE TABLE IF NOT EXISTS pipeline_artifacts",
        "CREATE TABLE IF NOT EXISTS pipeline_artifact_lineage",
        "idx_pipeline_artifacts_kind_status",
        "idx_pipeline_artifacts_retention",
        "idx_pipeline_artifact_lineage_parent",
    ),
    "086_create_context_outbox_events.sql": (
        "CREATE TABLE IF NOT EXISTS outbox_events",
        "idx_outbox_events_unpublished",
        "idx_outbox_events_type_created",
    ),
    "087_create_draft_claim_observations.sql": (
        "CREATE TABLE IF NOT EXISTS draft_claim_observations",
        "CREATE TABLE IF NOT EXISTS draft_claim_observation_possible_questions",
        "idx_draft_claim_observations_source_unit",
        "idx_draft_claim_observation_questions_observation",
    ),
    "088_create_claim_extraction_stage_work_item_index.sql": (
        "CREATE TABLE IF NOT EXISTS claim_extraction_stage_work_items",
        "idx_claim_extraction_stage_work_items_stage",
        "idx_claim_extraction_stage_work_items_work_item",
        "idx_pipeline_artifacts_claim_extraction_stage_payload",
    ),
    "089_create_draft_claim_observation_provenance.sql": (
        "CREATE TABLE IF NOT EXISTS draft_claim_observation_provenance",
        "observation_ref text PRIMARY KEY REFERENCES draft_claim_observations",
        "workflow_run_id text NOT NULL",
        "stage_run_id text NOT NULL",
        "work_item_id text NOT NULL",
        "work_item_attempt_id text NOT NULL",
        "llm_task_id text NOT NULL",
        "llm_attempt_id text NOT NULL",
        "raw_artifact_ref text NOT NULL",
        "parsed_artifact_ref text NOT NULL",
        "claim_index integer NOT NULL",
        "idx_draft_claim_observation_provenance_stage",
        "idx_draft_claim_observation_provenance_artifacts",
    ),
    "090_create_knowledge_extraction_saga_tables.sql": (
        "CREATE TABLE IF NOT EXISTS knowledge_extraction_workflow_runs",
        "CREATE TABLE IF NOT EXISTS knowledge_extraction_phase_checkpoints",
        "CREATE TABLE IF NOT EXISTS knowledge_extraction_command_log",
        "CREATE TABLE IF NOT EXISTS knowledge_extraction_event_cursor",
        "idx_knowledge_extraction_workflow_runs_project",
        "idx_knowledge_extraction_workflow_runs_source_document",
        "idx_knowledge_extraction_workflow_runs_status_phase",
        "idx_knowledge_extraction_phase_checkpoints_phase_status",
        "idx_knowledge_extraction_command_log_workflow_phase",
        "idx_knowledge_extraction_event_cursor_workflow",
    ),
    "091_create_source_management_tables.sql": (
        "CREATE TABLE IF NOT EXISTS source_documents",
        "CREATE TABLE IF NOT EXISTS source_units",
        "idx_source_documents_project",
        "idx_source_documents_content_hash",
        "idx_source_units_document",
        "idx_source_units_document_ordinal",
    ),
}

FORBIDDEN_LEGACY_MARKERS = (
    "knowledge_workbench_section_batch_queue_items",
    "knowledge_workbench_parallel_section_batch_plans",
    "knowledge_workbench_section_batch_plans",
    "knowledge_workbench_section_work_items",
    "knowledge_workbench_processing_runs",
    "knowledge_workbench_processing_node_runs",
    "knowledge_workbench_processing_node_artifacts",
    "CLAIM_OBSERVATIONS_PERSISTED",
    "REGISTRY_APPLICATION_QUEUED",
    "REGISTRY_APPLICATION_APPLIED",
    "WAITING_FOR_FRESH_REGISTRY",
    "ProcessingNodeRun",
    "ProcessingNodeArtifact",
    "SectionBatchQueueItem",
    "workbench_parallel_processing",
    "process_workbench_document",
)

REQUIRED_TABLES = (
    "execution_work_items",
    "execution_work_item_attempts",
    "llm_tasks",
    "llm_attempts",
    "pipeline_artifacts",
    "pipeline_artifact_lineage",
    "outbox_events",
    "draft_claim_observations",
    "draft_claim_observation_possible_questions",
    "claim_extraction_stage_work_items",
    "draft_claim_observation_provenance",
    "knowledge_extraction_workflow_runs",
    "knowledge_extraction_phase_checkpoints",
    "knowledge_extraction_command_log",
    "knowledge_extraction_event_cursor",
    "source_documents",
    "source_units",
)


def _read_migration(filename: str) -> str:
    path = MIGRATIONS / filename
    assert path.exists(), f"missing migration: {path}"
    return path.read_text(encoding="utf-8")


def test_new_context_persistence_migrations_exist_and_define_expected_tables() -> None:
    for filename, required_fragments in EXPECTED_MIGRATIONS.items():
        text = _read_migration(filename)
        missing = [fragment for fragment in required_fragments if fragment not in text]
        assert not missing, f"{filename} is missing required fragments:\n" + "\n".join(missing)


def test_new_context_persistence_migrations_do_not_reference_legacy_workbench_tables() -> None:
    offenders: list[str] = []
    for filename in EXPECTED_MIGRATIONS:
        text = _read_migration(filename)
        for marker in FORBIDDEN_LEGACY_MARKERS:
            if marker in text:
                offenders.append(f"{filename} contains forbidden marker {marker!r}")
    assert not offenders, "\n".join(offenders)


def test_new_context_persistence_migrations_use_canonical_table_names_once() -> None:
    all_text = "\n".join(_read_migration(filename) for filename in EXPECTED_MIGRATIONS)
    missing = [table for table in REQUIRED_TABLES if table not in all_text]
    assert not missing, "\n".join(missing)


def test_source_management_migration_defines_canonical_source_persistence() -> None:
    text = _read_migration("091_create_source_management_tables.sql")
    required = (
        "CREATE TABLE IF NOT EXISTS source_documents",
        "document_ref text PRIMARY KEY",
        "project_id text NOT NULL",
        "source_format text NOT NULL",
        "content_hash text NOT NULL",
        "original_filename text NULL",
        "created_at timestamptz NOT NULL",
        "CHECK (btrim(document_ref) <> '')",
        "CHECK (btrim(project_id) <> '')",
        "CHECK (btrim(source_format) <> '')",
        "CHECK (btrim(content_hash) <> '')",
        "CREATE TABLE IF NOT EXISTS source_units",
        "unit_ref text PRIMARY KEY",
        "document_ref text NOT NULL REFERENCES source_documents(document_ref) ON DELETE CASCADE",
        "unit_kind text NOT NULL",
        "text text NOT NULL",
        "heading_path jsonb NOT NULL DEFAULT '[]'::jsonb",
        "lineage jsonb NOT NULL DEFAULT '{}'::jsonb",
        "ordinal integer NOT NULL",
        "CHECK (jsonb_typeof(heading_path) = 'array')",
        "CHECK (jsonb_typeof(lineage) = 'object')",
        "UNIQUE (document_ref, ordinal)",
        "idx_source_documents_project",
        "idx_source_documents_content_hash",
        "idx_source_units_document",
        "idx_source_units_document_ordinal",
    )
    forbidden = (
        "knowledge_workbench_documents",
        "knowledge_workbench_document_sections",
        "knowledge_workbench_processing_runs",
        "SectionBatchQueueItem",
        "workbench_parallel_processing",
        "process_workbench_document",
    )
    missing = [fragment for fragment in required if fragment not in text]
    offenders = [marker for marker in forbidden if marker in text]
    assert not missing, "\n".join(missing)
    assert not offenders, "\n".join(offenders)


def test_knowledge_extraction_saga_migration_defines_canonical_durable_state() -> None:
    text = _read_migration("090_create_knowledge_extraction_saga_tables.sql")
    required = (
        "CREATE TABLE IF NOT EXISTS knowledge_extraction_workflow_runs",
        "CREATE TABLE IF NOT EXISTS knowledge_extraction_phase_checkpoints",
        "CREATE TABLE IF NOT EXISTS knowledge_extraction_command_log",
        "CREATE TABLE IF NOT EXISTS knowledge_extraction_event_cursor",
        "workflow_run_id text PRIMARY KEY",
        "project_id text NOT NULL",
        "source_document_ref text NOT NULL",
        "status text NOT NULL",
        "current_phase text NOT NULL",
        "CHECK (status <> 'COMPLETED' OR completed_at IS NOT NULL)",
        "CHECK (status <> 'CANCELLED' OR cancelled_at IS NOT NULL)",
        "CHECK (jsonb_typeof(checkpoint_payload) = 'object')",
        "PRIMARY KEY (workflow_run_id, phase_key)",
    )
    forbidden = (
        "knowledge_workbench_processing_runs",
        "SectionBatchQueueItem",
        "workbench_parallel_processing",
        "process_workbench_document",
    )
    missing = [fragment for fragment in required if fragment not in text]
    offenders = [marker for marker in forbidden if marker in text]
    assert not missing, "\n".join(missing)
    assert not offenders, "\n".join(offenders)
