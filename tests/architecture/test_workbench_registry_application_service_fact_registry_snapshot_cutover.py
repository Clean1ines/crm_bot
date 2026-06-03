from pathlib import Path


SERVICE = Path("src/application/services/faq_workbench_registry_application_service.py")


def test_registry_application_service_applies_fact_registry_snapshot_not_surface_entries() -> None:
    source = SERVICE.read_text(encoding="utf-8")

    assert "ApplyFactRegistrySnapshotCommand" in source
    assert "apply_fact_registry_snapshot" in source
    assert "fact_registry" in source
    assert "create_registry_snapshot" in source

    forbidden = (
        "ApplyRegistryFindingsCommand",
        "apply_findings_to_registry",
        "QuestionRegistryEntry",
        "RegistryUpdateApplication",
        "RegistryUpdateOperation",
        "ClaimObservationRecord",
        "ClaimObservationAction",
        "ClaimObservationStatus",
        "upsert_question_registry_entries",
        "create_registry_update_applications",
        "apply_registry_update",
        "relation_proposal_from_questions",
        "decide_registry_merge",
        "canonical_question",
        "answer_delta",
        "surface_key",
    )

    for token in forbidden:
        assert token not in source
