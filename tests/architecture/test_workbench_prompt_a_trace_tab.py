from pathlib import Path


MODAL = Path(
    "frontend/src/pages/knowledge/components/KnowledgeDocumentCurationModal.tsx"
)
API = Path("frontend/src/shared/api/modules/knowledge.ts")
SERVICE = Path("src/application/workbench_observability/evidence_trace.py")
REPOSITORY = Path("src/infrastructure/db/workbench_observability_repository.py")


def test_trace_modal_has_prompt_a_tab_via_evidence_trace() -> None:
    source = MODAL.read_text(encoding="utf-8")

    assert "knowledgeApi.evidenceTrace" in source
    assert "Prompt A: обработанные секции и claims" in source
    assert "prompt_a" in source
    assert "Prompt A processed" in source
    assert "activeTab === 'sections'" not in source
    assert "Секции и claims" not in source


def test_prompt_a_tab_keeps_canonical_and_surface_views_out_of_section_claims() -> None:
    source = MODAL.read_text(encoding="utf-8")
    prompt_a_block = source.split("activeTab === 'prompt_a'", 1)[1].split(
        "activeTab === 'facts'",
        1,
    )[0]

    assert "Извлечённые claims" in prompt_a_block
    assert "Canonical facts из этой секции" not in prompt_a_block
    assert "Surfaces из этой секции" not in prompt_a_block


def test_evidence_trace_contract_exposes_prompt_a_details() -> None:
    api = API.read_text(encoding="utf-8")
    service = SERVICE.read_text(encoding="utf-8")
    repository = REPOSITORY.read_text(encoding="utf-8")

    for marker in (
        "granularity",
        "scope",
        "exclusion_scope",
        "triples",
        "local_relations",
        "node_run_id",
        "artifact_id",
    ):
        assert marker in api
        assert marker in service
        assert marker in repository

    assert "payload_json->'claim_observations'" in repository
    assert "node.node_name = 'faq_surface_claim_observations'" in repository
