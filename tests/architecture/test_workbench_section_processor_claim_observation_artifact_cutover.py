from pathlib import Path


SERVICE = Path(
    "src/application/services/faq_workbench_section_work_item_processor_service.py"
)


def test_section_processor_no_longer_runs_prompt_c_from_claim_observation_artifacts() -> (
    None
):
    source = SERVICE.read_text(encoding="utf-8")

    assert "process_claim_observations_persisted_section_work_item" in source
    assert "claim_observations_persisted_item=queue_item" in source

    forbidden = (
        "claim_inputs=claim_observations",
        "generate_registry_updates(",
        "persist_registry_merge_output(",
        "_load_claim_observations_for_node_run",
        "get_processing_node_artifact_by_node_run_id_and_type",
        "list_section_findings_by_node_run_id",
        "tuple(finding.finding_id for finding in findings)",
        "section_findings=claim_observations",
        "section_findings=findings",
        "SectionFinding,",
    )
    for token in forbidden:
        assert token not in source
