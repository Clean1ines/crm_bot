from pathlib import Path


WORKBENCH_MIGRATIONS = (
    Path("migrations/070_create_faq_workbench_v1.sql"),
    Path("migrations/071_workbench_publish_retention_cutover.sql"),
    Path("migrations/072_workbench_registry_update_proposals.sql"),
    Path("migrations/073_create_workbench_registry_application_queue.sql"),
    Path("migrations/073_workbench_parallel_section_batch_queue.sql"),
    Path("migrations/073_workbench_section_batch_queue.sql"),
)


def test_workbench_migrations_define_fact_registry_schema_not_surface_question_schema() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in WORKBENCH_MIGRATIONS)

    required = (
        "knowledge_workbench_fact_registries",
        "knowledge_workbench_canonical_facts",
        "knowledge_workbench_fact_triples",
        "knowledge_workbench_fact_mentions",
        "knowledge_workbench_fact_relations",
        "knowledge_workbench_fact_registry_application_queue",
        "claim_observations_node_run_id",
        "claim_input_refs",
        "fact_registry_payload",
    )
    for token in required:
        assert token in combined

    forbidden = (
        "knowledge_workbench_question_registries",
        "knowledge_workbench_question_registry_entries",
        "knowledge_workbench_claim_observations",
        "knowledge_workbench_registry_update_proposals",
        "knowledge_workbench_surfaces",
        "knowledge_workbench_surface_materialization_results",
        "knowledge_workbench_surface_curation_sessions",
        "knowledge_workbench_surface_curation_changes",
        "claim_observations_node_run_id",
        "claim_input_refs",
        "source_finding_id",
        "target_surface_key",
        "local_surface_key",
        "canonical_question",
        "surface_kind",
        "answer_delta",
        "question_scope",
        "evidence_quotes",
        "registry_updates",
    )
    for token in forbidden:
        assert token not in combined
