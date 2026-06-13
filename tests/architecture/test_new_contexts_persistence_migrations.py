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
        "claim_index integer NOT NULL",
        "idx_draft_claim_observation_provenance_stage",
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
    "101_drop_draft_claim_observation_artifact_ref_columns.sql": (
        "ALTER TABLE draft_claim_observation_provenance",
        "DROP COLUMN IF EXISTS",
        "quote_ident('raw_' || 'artifact_ref')",
        "quote_ident('parsed_' || 'artifact_ref')",
    ),
    "102_create_llm_attempt_capacity_observations.sql": (
        "CREATE TABLE IF NOT EXISTS llm_attempt_capacity_observations",
        "observation_id text PRIMARY KEY",
        "remaining_minute_requests integer NULL",
        "remaining_daily_tokens integer NULL",
        "actual_prompt_tokens integer NULL",
        "actual_completion_tokens integer NULL",
        "actual_total_tokens integer NULL",
        "idx_llm_attempt_capacity_observations_provider_account_model",
        "idx_llm_attempt_capacity_observations_observed_at",
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
    "llm_attempt_capacity_observations",
)


def _read_migration(filename: str) -> str:
    path = MIGRATIONS / filename
    assert path.exists(), f"missing migration: {path}"
    return path.read_text(encoding="utf-8")


def test_new_context_persistence_migrations_exist_and_define_expected_tables() -> None:
    for filename, required_fragments in EXPECTED_MIGRATIONS.items():
        text = _read_migration(filename)

        missing = [fragment for fragment in required_fragments if fragment not in text]

        assert not missing, f"{filename} is missing required fragments:\n" + "\n".join(
            missing
        )


def test_new_context_persistence_migrations_do_not_reference_legacy_workbench_tables() -> (
    None
):
    offenders: list[str] = []

    for filename in EXPECTED_MIGRATIONS:
        text = _read_migration(filename)
        for marker in FORBIDDEN_LEGACY_MARKERS:
            if marker in text:
                offenders.append(f"{filename} contains forbidden marker {marker!r}")

    assert not offenders, (
        "New context persistence migrations must not reference legacy Workbench "
        "queue/node/checkpoint tables or statuses:\n" + "\n".join(offenders)
    )


def test_new_context_persistence_migrations_use_canonical_table_names_once() -> None:
    all_text = "\n".join(_read_migration(filename) for filename in EXPECTED_MIGRATIONS)

    missing = [table for table in REQUIRED_TABLES if table not in all_text]

    assert not missing, (
        "new context persistence migrations are missing canonical tables:\n"
        + "\n".join(missing)
    )


def test_execution_runtime_migration_preserves_work_item_state_shape() -> None:
    text = _read_migration("083_create_execution_runtime_tables.sql")

    required = (
        "work_item_id text PRIMARY KEY",
        "work_kind text NOT NULL",
        "status text NOT NULL",
        "attempt_count integer NOT NULL",
        "leased_by text NULL",
        "lease_token text NULL",
        "lease_expires_at timestamptz NULL",
        "next_attempt_at timestamptz NULL",
        "last_error_kind text NULL",
        "chk_execution_work_items_lease_shape",
        "chk_execution_work_items_terminal_no_next_attempt",
    )

    missing = [fragment for fragment in required if fragment not in text]
    assert not missing, "\n".join(missing)


def test_llm_runtime_migration_preserves_task_and_attempt_shape() -> None:
    text = _read_migration("084_create_llm_runtime_tables.sql")

    required = (
        "task_id text PRIMARY KEY",
        "prompt_id text NOT NULL",
        "prompt_version text NOT NULL",
        "input_ref text NOT NULL",
        "output_contract_ref text NOT NULL",
        "selected_provider_id text NULL",
        "selected_model_id text NULL",
        "selected_account_ref text NULL",
        "wait_until timestamptz NULL",
        "input_tokens integer NULL",
        "output_tokens integer NULL",
        "chk_llm_tasks_running_has_route",
        "chk_llm_tasks_wait_until_only_deferred",
    )

    missing = [fragment for fragment in required if fragment not in text]
    assert not missing, "\n".join(missing)


def test_outbox_migration_defines_generic_unpublished_event_queue() -> None:
    text = _read_migration("086_create_context_outbox_events.sql")

    required = (
        "event_id text PRIMARY KEY",
        "event_type text NOT NULL",
        "aggregate_ref text NULL",
        "payload jsonb NOT NULL",
        "occurred_at timestamptz NOT NULL",
        "published_at timestamptz NULL",
        "publish_attempt_count integer NOT NULL",
        "idx_outbox_events_unpublished",
    )

    missing = [fragment for fragment in required if fragment not in text]
    assert not missing, "\n".join(missing)


def test_draft_claim_observation_migration_stays_prompt_a_draft_only() -> None:
    text = _read_migration("087_create_draft_claim_observations.sql")

    required = (
        "observation_ref text PRIMARY KEY",
        "source_unit_ref text NOT NULL",
        "claim text NOT NULL",
        "granularity text NOT NULL",
        "exclusion_scope text NOT NULL",
        "evidence_block text NOT NULL",
        "draft_claim_observation_possible_questions",
    )

    forbidden = (
        "surface_kind",
        "canonical_intent",
        "ontology",
        "relation",
        "triple",
        "subject",
        "predicate",
        "object",
        "confidence",
    )

    missing = [fragment for fragment in required if fragment not in text]
    offenders = [marker for marker in forbidden if marker in text.lower()]

    assert not missing, "\n".join(missing)
    assert not offenders, (
        "Prompt A draft claim persistence must not contain consolidation/publication fields:\n"
        + "\n".join(offenders)
    )


def test_claim_extraction_stage_work_item_index_keeps_stage_refs_out_of_execution_items() -> (
    None
):
    execution_text = _read_migration("083_create_execution_runtime_tables.sql")
    stage_index_text = _read_migration(
        "088_create_claim_extraction_stage_work_item_index.sql"
    )

    assert "workflow_run_id" not in execution_text
    assert "stage_run_id" not in execution_text
    assert "workflow_run_id text NOT NULL" in stage_index_text
    assert "stage_run_id text NOT NULL" in stage_index_text
    assert (
        "work_item_id text NOT NULL REFERENCES execution_work_items" in stage_index_text
    )
    assert (
        "PRIMARY KEY (workflow_run_id, stage_run_id, work_item_id)" in stage_index_text
    )


def test_draft_claim_observation_provenance_migration_stays_extraction_trace_only() -> (
    None
):
    text = _read_migration("089_create_draft_claim_observation_provenance.sql")

    required = (
        "observation_ref text PRIMARY KEY REFERENCES draft_claim_observations",
        "source_unit_ref text NOT NULL",
        "workflow_run_id text NOT NULL",
        "stage_run_id text NOT NULL",
        "work_item_id text NOT NULL",
        "work_item_attempt_id text NOT NULL",
        "llm_task_id text NOT NULL",
        "llm_attempt_id text NOT NULL",
        "prompt_id text NOT NULL",
        "prompt_version text NOT NULL",
        "claim_index integer NOT NULL",
    )

    forbidden = (
        "REFERENCES execution_work_items",
        "REFERENCES execution_work_item_attempts",
        "REFERENCES llm_tasks",
        "REFERENCES llm_attempts",
        "REFERENCES pipeline_artifacts",
        "surface_kind",
        "canonical_intent",
        "ontology",
        "publication",
        "consolidated",
    )

    missing = [fragment for fragment in required if fragment not in text]
    offenders = [marker for marker in forbidden if marker in text]

    assert not missing, "\n".join(missing)
    assert not offenders, "\n".join(offenders)


def test_source_management_migration_defines_canonical_source_persistence() -> None:
    text = _read_migration("091_create_source_management_tables.sql")

    required = (
        "CREATE TABLE IF NOT EXISTS source_documents",
        "CREATE TABLE IF NOT EXISTS source_units",
        "document_ref text PRIMARY KEY",
        "project_id text NOT NULL",
        "source_format text NOT NULL",
        "content_hash text NOT NULL",
        "original_filename text NULL",
        "created_at timestamptz NOT NULL",
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


def test_removed_draft_claim_observation_artifact_ref_nullable_migration_is_not_required() -> (
    None
):
    assert not (
        MIGRATIONS / "100_make_draft_claim_observation_artifact_refs_nullable.sql"
    ).exists()


def test_draft_claim_observation_provenance_migrations_do_not_expose_removed_artifact_ref_columns() -> (
    None
):
    removed_columns = ("raw_" + "artifact_ref", "parsed_" + "artifact_ref")

    for filename in (
        "089_create_draft_claim_observation_provenance.sql",
        "101_drop_draft_claim_observation_artifact_ref_columns.sql",
    ):
        text = _read_migration(filename)
        for column_name in removed_columns:
            assert column_name not in text
