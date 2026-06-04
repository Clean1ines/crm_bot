from pathlib import Path


ORCHESTRATOR = Path(
    "src/application/services/faq_workbench_document_processing_orchestrator.py"
)
CLAIM_OBSERVATIONS_SERVICE = Path(
    "src/application/services/faq_workbench_claim_observations_service.py"
)


def _join(*parts: str) -> str:
    return "".join(parts)


def test_retired_markdown_document_generator_test_no_longer_imports_old_sequential_contract() -> (
    None
):
    source = Path(__file__).read_text(encoding="utf-8")
    import_block = source.split("ORCHESTRATOR =", 1)[0]

    forbidden_import_markers = (
        _join("Process", "Markdown", "Document", "Command"),
        _join("Parsed", "Section", "Finding"),
        _join("Claim", "Observations", "Input"),
        _join("Section", "Finding", "Action"),
        "SurfaceKind",
    )

    for marker in forbidden_import_markers:
        assert marker not in import_block


def test_legacy_sequential_orchestrator_is_not_the_prompt_c_parallel_runtime_contract() -> (
    None
):
    orchestrator = ORCHESTRATOR.read_text(encoding="utf-8")
    claim_observations_service = CLAIM_OBSERVATIONS_SERVICE.read_text(encoding="utf-8")

    assert _join("Process", "Markdown", "Document", "Command") not in orchestrator
    assert _join("process", "_markdown", "_document") not in orchestrator
    assert _join("Parsed", "Section", "Finding") not in claim_observations_service

    assert "claim_observations" in claim_observations_service
    assert (
        "canonicalization" in orchestrator
        or "process_existing_document" in orchestrator
    )
