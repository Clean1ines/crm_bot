from pathlib import Path

SERVICE = Path("src/application/services/faq_workbench_claim_observations_service.py")


def test_claim_observations_service_persists_claim_observations_as_node_artifacts_not_old_rows() -> (
    None
):
    source = SERVICE.read_text(encoding="utf-8")
    assert "claim_observations: tuple[ClaimObservation" in source
    assert "claim_observation_ids" in source
    assert '"claim_observations"' in source
    assert "ProcessingNodeArtifactType.PARSED_LLM_OUTPUT" in source
    assert "ProcessingNodeArtifactType.RAW_LLM_OUTPUT" in source

    for token in (
        "class ParsedClaimObservationRecord",
        "parsed_findings",
        "ClaimObservationAction",
        "ClaimObservationStatus",
        "SurfaceKind",
        "create_claim_observations(claim_observations)",
        "def _to_section_finding",
        "tuple[ClaimObservationRecord",
    ):
        assert token not in source
