from pathlib import Path

SECTION_WORKER = Path(
    "src/application/services/faq_workbench_section_work_item_processor_service.py"
)
REGISTRY_MERGE_PORT = Path("src/application/ports/faq_workbench_registry_merge_generator.py")
GRAPH_ALIGNMENT = Path("src/domain/project_plane/knowledge_workbench/graph_alignment.py")


def test_section_worker_no_longer_builds_graph_alignment_candidates_for_prompt_c() -> None:
    source = SECTION_WORKER.read_text(encoding="utf-8")

    forbidden_markers = (
        "CandidateFactSet",
        "candidate_fact_sets",
        "_candidate_fact_sets_for_claim_observations",
        "_candidate_facts_for_claim_observation",
        "claim_inputs=claim_observations",
    )
    for marker in forbidden_markers:
        assert marker not in source


def test_graph_alignment_candidates_remain_only_in_graph_alignment_domain_not_prompt_c_port() -> None:
    graph_alignment = GRAPH_ALIGNMENT.read_text(encoding="utf-8")
    registry_merge_port = REGISTRY_MERGE_PORT.read_text(encoding="utf-8")

    assert "class CandidateFactSet" in graph_alignment

    forbidden_port_markers = (
        "CandidateFactSet",
        "candidate_fact_sets",
        "claim_inputs",
        "match_context",
    )
    for marker in forbidden_port_markers:
        assert marker not in registry_merge_port
