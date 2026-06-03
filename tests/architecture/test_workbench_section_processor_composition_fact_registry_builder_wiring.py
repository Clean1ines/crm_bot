from pathlib import Path

COMPOSITION = Path("src/interfaces/composition/faq_workbench_parallel_processing.py")


def test_section_processor_composition_wires_extraction_only_dependencies() -> None:
    source = COMPOSITION.read_text(encoding="utf-8")

    assert "FaqWorkbenchSectionWorkItemProcessorService" in source
    assert "FaqWorkbenchClaimObservationsRunner" in source
    assert "claim_observations_runner=FaqWorkbenchClaimObservationsRunner" in source
    assert "id_factory=dependencies.id_factory" in source

    assert "registry_merge_generator" not in source
    assert "registry_merge_service" not in source
    assert "FaqWorkbenchRegistryMergeService" not in source
    assert "make_workbench_registry_merge_generator" not in source
