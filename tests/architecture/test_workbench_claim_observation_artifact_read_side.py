from __future__ import annotations

from pathlib import Path

PORT = Path("src/application/ports/knowledge_workbench.py")
REPOSITORY = Path("src/infrastructure/db/knowledge_workbench_repository.py")


def test_claim_observation_artifact_read_side_is_explicit_document_run_api() -> None:
    port_source = PORT.read_text(encoding="utf-8")
    repository_source = REPOSITORY.read_text(encoding="utf-8")

    assert "list_claim_observation_parsed_artifacts" in port_source
    assert "list_claim_observation_parsed_artifacts" in repository_source

    assert "ProcessingNodeName.FAQ_SURFACE_SECTION_FINDINGS.value" in repository_source
    assert "ProcessingNodeArtifactType.PARSED_LLM_OUTPUT.value" in repository_source

    assert "project_id: str" in port_source
    assert "document_id: str" in port_source
    assert "processing_run_id: str" in port_source
    assert "tuple[ProcessingNodeArtifact, ...]" in port_source


def test_claim_observation_artifact_read_side_orders_by_section_index() -> None:
    repository_source = REPOSITORY.read_text(encoding="utf-8")

    assert (
        "LEFT JOIN knowledge_workbench_document_sections AS section"
        in repository_source
    )
    assert "ORDER BY" in repository_source
    assert "section.section_index" in repository_source
    assert "artifact.created_at" in repository_source


def test_claim_observation_artifact_read_side_uses_artifact_payload_not_old_rows() -> (
    None
):
    repository_source = REPOSITORY.read_text(encoding="utf-8")

    method_start = repository_source.index(
        "async def list_claim_observation_parsed_artifacts"
    )
    method_end = repository_source.find("\n    async def ", method_start + 1)
    if method_end == -1:
        method_end = len(repository_source)
    method_source = repository_source[method_start:method_end]

    assert "knowledge_workbench_processing_node_artifacts" in method_source
    assert "payload_json" in method_source
    assert "claim_observations" not in method_source
    assert "knowledge_workbench_claim_observations" not in method_source
