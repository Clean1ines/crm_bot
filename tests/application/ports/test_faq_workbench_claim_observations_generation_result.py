from pathlib import Path

from src.application.ports import faq_workbench_claim_observations_generator as port


PORT = Path("src/application/ports/faq_workbench_claim_observations_generator.py")


def test_claim_observations_contract_is_extraction_only_source_unit_to_local_graph() -> (
    None
):
    source = PORT.read_text(encoding="utf-8")

    assert port.FaqWorkbenchClaimObservationsGenerationResult is not None
    assert "ClaimObservation" in port.__all__
    assert "source_unit -> local claims/local graph" in source
    assert "known_facts" not in source
    assert "relation_to_known_claim" not in source
    assert "suggested_registry_action" not in source


def test_generation_result_preserves_claim_observations_collection_protocol() -> None:
    source = PORT.read_text(encoding="utf-8")

    assert "claim_observations: tuple[ClaimObservation, ...]" in source
    assert "def findings(" in source
    assert "def claim_observation_count(" in source
    assert "def __iter__(" in source
    assert "def __len__(" in source
    assert "def __getitem__(" in source
