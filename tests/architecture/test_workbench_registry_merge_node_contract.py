from __future__ import annotations

from pathlib import Path


GRAPH = Path("src/application/workbench/processing_graph_contract.py")
PORT = Path("src/application/ports/faq_workbench_registry_merge_generator.py")
GENERATOR = Path("src/infrastructure/llm/faq_workbench_registry_merge_generator.py")
SERVICE = Path("src/application/services/faq_workbench_registry_merge_service.py")
PROMPT = Path("src/agent/prompts/faq_surface_registry_merge.ru.txt")
MIGRATION_072 = Path("migrations/072_workbench_registry_update_proposals.sql")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _registry_merge_graph_block() -> str:
    source = _read(GRAPH)
    lines = source.splitlines()
    operation_index = next(
        index
        for index, line in enumerate(lines)
        if 'operation_name="faq_surface_registry_merge"' in line
    )

    start = None
    for index in range(operation_index, -1, -1):
        line = lines[index]
        if (
            "ProcessingNodeSpec(" in line
            or "WorkbenchProcessingNodeSpec(" in line
            or "NodeSpec(" in line
        ):
            start = index
            break

    assert start is not None

    balance = 0
    end = None
    for index in range(start, len(lines)):
        balance += lines[index].count("(")
        balance -= lines[index].count(")")
        if index > start and balance <= 0:
            end = index
            break

    assert end is not None
    return "\n".join(lines[start : end + 1])


def _old_claim_inputs_marker() -> str:
    return "claim" + "_inputs"


def _old_candidate_sets_marker() -> str:
    return "candidate" + "_fact_sets"


def _old_source_unit_marker() -> str:
    return "source" + "_unit"


def _old_match_context_marker() -> str:
    return "match" + "_context"


def _old_registry_updates_marker() -> str:
    return "registry" + "_updates"


def test_registry_merge_node_graph_contract_uses_canonicalization_unit_inputs() -> None:
    block = _registry_merge_graph_block()

    assert '"canonicalization_unit"' in block
    assert '"registry_snapshot_payload"' in block
    assert '"relevant_registry_state"' in block
    assert '"canonical_facts"' in block

    assert _old_source_unit_marker() not in block
    assert '"registry_snapshot"' not in block
    assert _old_match_context_marker() not in block


def test_registry_merge_node_graph_contract_outputs_fact_registry_snapshot_payload() -> (
    None
):
    block = _registry_merge_graph_block()

    assert '"fact_registry"' in block
    assert '"registry_update_summary"' in block
    assert '"warnings"' in block
    assert '"metrics"' in block
    assert _old_registry_updates_marker() not in block


def test_registry_merge_node_graph_contract_uses_fact_registry_canonicalization_route() -> (
    None
):
    block = _registry_merge_graph_block()

    assert 'operation_name="faq_surface_registry_merge"' in block
    assert 'route_purpose="workbench_fact_registry_canonicalization"' in block
    assert 'route_purpose="workbench_registry_merge"' not in block


def test_prompt_c_port_contract_uses_canonicalization_unit_not_old_section_merge_inputs() -> (
    None
):
    source = _read(PORT)

    assert "FaqWorkbenchRegistryMergeGenerationCommand" in source
    assert "LocalClaimCanonicalizationUnit" in source
    assert "canonicalization_unit:" in source
    assert "registry_snapshot_payload:" in source
    assert "relevant_registry_state:" in source
    assert "canonical_facts:" in source

    assert "DocumentSection" not in source
    assert "CandidateFactSet" not in source
    assert _old_claim_inputs_marker() not in source
    assert _old_candidate_sets_marker() not in source
    assert _old_match_context_marker() not in source


def test_prompt_c_port_result_exposes_fact_registry_counts_not_old_advisory_rows() -> (
    None
):
    source = _read(PORT)

    assert "fact_registry:" in source
    assert "registry_update_summary:" in source
    assert "canonical_fact_count" in source
    assert "fact_relation_count" in source

    assert "proposal_count" not in source
    assert "def proposals" not in source
    # Method name generate_registry_updates is still the public port API.
    # What is forbidden here is the old JSON payload key.
    assert '"' + _old_registry_updates_marker() + '"' not in source


def test_prompt_c_generator_builds_payload_from_canonicalization_unit_and_registry_state() -> (
    None
):
    source = _read(GENERATOR)

    assert "command.canonicalization_unit.to_prompt_payload()" in source
    assert '"canonicalization_unit"' in source
    assert '"registry_snapshot_payload"' in source
    assert '"relevant_registry_state"' in source
    assert '"canonical_facts"' in source

    assert "command.section" not in source
    assert "command.claim_inputs" not in source
    assert "command.candidate_fact_sets" not in source
    assert "command.match_context" not in source
    assert _old_claim_inputs_marker() not in source
    assert _old_candidate_sets_marker() not in source
    assert _old_source_unit_marker() not in source
    assert _old_match_context_marker() not in source


def test_prompt_c_generator_parses_full_fact_registry_snapshot_contract() -> None:
    source = _read(GENERATOR)

    assert "parse_fact_registry_payload" in source
    assert '"fact_registry"' in source
    assert '"registry_update_summary"' in source
    assert '"canonical_facts"' in source
    assert '"fact_relations"' in source
    assert "duplicate canonical fact id" in source
    assert "unknown target_fact_id" in source

    # Method name generate_registry_updates is still the public port API.
    # What is forbidden here is the old JSON payload key.
    assert '"' + _old_registry_updates_marker() + '"' not in source


def test_prompt_c_generator_remains_infrastructure_boundary_only() -> None:
    source = _read(GENERATOR)

    assert "LlmJsonInvocationPort" in source
    assert "LlmJsonInvocationRequest" in source
    assert "FaqWorkbenchRegistryMergeGeneratorPort" in source
    assert "create_registry_snapshot" not in source
    assert "create_processing_node_artifact" not in source
    assert "KnowledgeWorkbenchRepository" not in source


def test_prompt_c_prompt_file_uses_cluster_canonicalization_language() -> None:
    source = _read(PROMPT)

    assert "canonicalization_unit" in source
    assert "registry_snapshot_payload" in source
    assert "relevant_registry_state" in source
    assert "canonical_facts" in source
    assert "fact_registry" in source
    assert "registry_update_summary" in source

    assert _old_claim_inputs_marker() not in source
    assert _old_candidate_sets_marker() not in source
    assert _old_source_unit_marker() not in source
    assert _old_match_context_marker() not in source


def test_registry_merge_persistence_service_is_document_level_canonicalization_node() -> (
    None
):
    source = _read(SERVICE)

    assert "LocalClaimCanonicalizationUnit" in source
    assert "PersistRegistryMergeNodeOutputCommand" in source
    assert "ProcessRegistryMergeGenerationErrorCommand" in source
    assert "canonicalization_unit:" in source
    assert "section_id=None" in source
    assert '"canonicalization_unit_id"' in source
    assert '"canonicalization_member_section_ids"' in source
    assert '"contract": "fact_registry_canonicalization"' in source


def test_registry_merge_persistence_service_persists_llm_artifacts_without_applying_snapshot() -> (
    None
):
    source = _read(SERVICE)

    assert "create_processing_node_run" in source
    assert "create_processing_node_artifact" in source
    assert "RAW_LLM_OUTPUT" in source
    assert "PARSED_LLM_OUTPUT" in source
    assert "sync_processing_run_llm_usage_totals" in source

    assert "create_registry_snapshot" not in source
    assert "apply_fact_registry_snapshot" not in source
    assert "create_registry_update_proposals" not in source
    assert "upsert_fact_registry_entries" not in source


def test_registry_merge_error_lifecycle_persists_canonicalization_unit_context() -> (
    None
):
    source = _read(SERVICE)

    assert "persist_registry_merge_generation_error" in source
    assert "persist_registry_merge_generation_error_lifecycle" in source
    assert (
        '"canonicalization_unit": command.canonicalization_unit.to_prompt_payload()'
        in source
    )
    assert '"canonicalization_unit_id"' in source
    assert "ProcessingNodeStatus.FAILED" in source
    assert "ERROR_REPORT" in source


def test_registry_update_proposal_migration_is_retired_after_fact_registry_cutover() -> (
    None
):
    source = _read(MIGRATION_072)

    assert "Intentionally no-op" in source
    assert "Prompt C produces fact_registry snapshots/artifacts directly" in source
    assert (
        "CREATE TABLE IF NOT EXISTS knowledge_workbench_registry_update_proposals"
        not in source
    )


def test_registry_merge_architecture_does_not_require_nonexistent_renamed_files() -> (
    None
):
    assert PORT.exists()
    assert GENERATOR.exists()
    assert SERVICE.exists()

    assert not Path(
        "src/application/ports/faq_workbench_"
        + "fact_registry_canonicalization"
        + "_generator.py"
    ).exists()
    assert not Path(
        "src/infrastructure/llm/faq_workbench_"
        + "fact_registry_canonicalization"
        + "_generator.py"
    ).exists()
    assert not Path(
        "src/application/services/faq_workbench_"
        + "fact_registry_canonicalization"
        + "_service.py"
    ).exists()


def test_registry_merge_contract_keeps_legacy_compiler_modules_retired() -> None:
    generator_source = _read(GENERATOR)
    service_source = _read(SERVICE)
    port_source = _read(PORT)

    combined = "\n".join((generator_source, service_source, port_source))

    assert "knowledge_surface_compiler" not in combined
    assert "knowledge_surface_parallel_graph_compiler" not in combined
    assert "knowledge_surface_staged_compiler" not in combined
    assert "KnowledgeSurface" not in combined
