from pathlib import Path


SERVICE = Path("src/application/services/faq_workbench_section_work_item_processor_service.py")


def test_claim_observations_persisted_recovery_is_extraction_queue_transition_not_prompt_c_builder() -> None:
    source = SERVICE.read_text(encoding="utf-8")
    start = source.index("async def process_claim_observations_persisted_section_work_item")
    end = source.index("async def process_one_section_work_item", start)
    body = source[start:end]

    assert "process_claim_observations_persisted_section_work_item" in body
    assert "claim_observations_persisted_item=queue_item" in body

    forbidden = (
        "claim_inputs=claim_observations",
        "generate_registry_updates(",
        "persist_registry_merge_output(",
        "create_registry_application_queue_item(",
        "list_claim_observations_by_node_run_id(",
        "_load_claim_observations_for_node_run(",
    )
    for marker in forbidden:
        assert marker not in body
