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


def test_artifact_runtime_migration_preserves_opaque_payload_and_lineage() -> None:
    text = _read_migration("085_create_artifact_runtime_tables.sql")

    required = (
        "artifact_ref text PRIMARY KEY",
        "artifact_kind text NOT NULL",
        "payload jsonb NOT NULL",
        "retention_policy_kind text NOT NULL",
        "pipeline_artifact_lineage",
        "parent_artifact_ref text NOT NULL",
        "chk_pipeline_artifacts_payload_is_object",
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


def test_draft_claim_observation_provenance_migration_stays_extraction_trace_only() -> None:
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
        "raw_artifact_ref text NOT NULL",
        "parsed_artifact_ref text NOT NULL",
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
