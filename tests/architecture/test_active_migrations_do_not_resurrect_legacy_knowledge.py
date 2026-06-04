from pathlib import Path


ACTIVE_MIGRATIONS = sorted(Path("migrations").glob("*.sql"))

FORBIDDEN_DEAD_TABLE_TOKENS = (
    "knowledge_answer_candidates",
    "knowledge_candidate_clusters",
    "knowledge_candidate_cluster_members",
    "knowledge_compiler_runs",
    "knowledge_compiler_batches",
    "knowledge_compilation_metrics",
    "knowledge_surfaces",
    "knowledge_surface_",
    "knowledge_workbench_question_registries",
    "knowledge_workbench_question_registry_entries",
    "knowledge_workbench_claim_observations",
    "knowledge_workbench_registry_update_proposals",
    "knowledge_workbench_registry_application_queue_items",
    "knowledge_workbench_section_batch_plans",
    "knowledge_workbench_section_work_items",
)

FORBIDDEN_DEAD_SEMANTIC_TOKENS = (
    "section_findings",
    "section_findings_node_run_id",
    "canonical_question",
    "surface_kind",
    "question_scope",
    "answer_delta",
    "local_surface_key",
    "target_surface_key",
    "finding_ids",
    "question_registry",
    "registry_updates",
)

REQUIRED_WORKBENCH_FACT_REGISTRY_TOKENS = (
    "claim_observations_node_run_id",
    "knowledge_workbench_documents",
    "knowledge_workbench_document_sections",
    "knowledge_workbench_fact_registries",
    "knowledge_workbench_canonical_facts",
    "knowledge_workbench_fact_triples",
    "knowledge_workbench_fact_mentions",
    "knowledge_workbench_fact_relations",
    "knowledge_workbench_fact_registry_application_queue",
    "claim_input_refs",
)


def _active_migration_text() -> str:
    return "\n".join(
        f"-- FILE: {path}\n{path.read_text(encoding='utf-8')}"
        for path in ACTIVE_MIGRATIONS
    )


def test_active_migrations_do_not_resurrect_deleted_legacy_tables() -> None:
    source = _active_migration_text()

    offenders = [token for token in FORBIDDEN_DEAD_TABLE_TOKENS if token in source]

    assert not offenders, "\n".join(offenders)


def test_active_migrations_do_not_resurrect_deleted_surface_semantics() -> None:
    source = _active_migration_text()

    offenders = [token for token in FORBIDDEN_DEAD_SEMANTIC_TOKENS if token in source]

    assert not offenders, "\n".join(offenders)


def test_active_migrations_define_current_workbench_fact_registry_schema() -> None:
    source = _active_migration_text()

    missing = [
        token
        for token in REQUIRED_WORKBENCH_FACT_REGISTRY_TOKENS
        if token not in source
    ]

    assert not missing, "\n".join(missing)


def test_retired_legacy_migrations_are_not_in_active_runner_glob() -> None:
    active_names = {path.name for path in ACTIVE_MIGRATIONS}

    retired_names = {
        "060_create_knowledge_compiler_trace.sql",
        "061_create_knowledge_compiler_batches.sql",
        "068_create_knowledge_surface_compilation_tables.sql",
        "069_extend_knowledge_surface_graph_v1.sql",
    }

    resurrected = sorted(active_names & retired_names)
    assert not resurrected, "\n".join(resurrected)
