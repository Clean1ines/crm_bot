from __future__ import annotations

from pathlib import Path


ORCH = Path(
    "src/application/services/faq_workbench_document_processing_orchestrator.py"
)
REGISTRY_MERGE_SERVICE = Path(
    "src/application/services/faq_workbench_registry_merge_service.py"
)
REGISTRY_MERGE_GENERATOR = Path(
    "src/infrastructure/llm/faq_workbench_registry_merge_generator.py"
)
QUEUE_HANDLER = Path("src/infrastructure/queue/handlers/workbench_document.py")
REGISTRY_APP_SERVICE = Path(
    "src/application/services/faq_workbench_registry_application_service.py"
)
WORKBENCH_PORT = Path("src/application/ports/knowledge_workbench.py")
WORKBENCH_REPO = Path("src/infrastructure/db/knowledge_workbench_repository.py")


def _read(path: Path) -> str:
    assert path.exists(), f"missing expected source file: {path}"
    return path.read_text(encoding="utf-8")


def test_registry_merge_persists_advisory_proposals_but_never_applies_them() -> None:
    service_source = _read(REGISTRY_MERGE_SERVICE)
    generator_source = _read(REGISTRY_MERGE_GENERATOR)
    orchestrator_source = _read(ORCH)
    handler_source = _read(QUEUE_HANDLER)

    assert "create_registry_update_proposals(" in service_source
    assert "RegistryUpdateProposal(" in generator_source
    assert "ProcessingNodeName.FAQ_SURFACE_REGISTRY_MERGE" in service_source
    assert "persist_registry_merge_generation_error" in service_source

    guarded_sources = {
        "registry_merge_service": service_source,
        "registry_merge_generator": generator_source,
        "orchestrator": orchestrator_source,
        "queue_handler": handler_source,
    }
    forbidden_markers = (
        "RegistryUpdateAppliedBy.LLM_ADVISORY",
        "RegistryUpdateApplication(",
        "create_registry_update_applications",
        "upsert_question_registry_entries",
    )

    for source_name, source in guarded_sources.items():
        for marker in forbidden_markers:
            assert marker not in source, f"{marker} leaked into {source_name}"


def test_registry_merge_runs_before_deterministic_application_without_feeding_it() -> (
    None
):
    orchestrator_source = _read(ORCH)

    merge_call_index = orchestrator_source.index(
        "await self._persist_registry_merge_advice_for_section("
    )
    deterministic_application_index = orchestrator_source.index(
        "await self._registry_application_service.apply_findings_to_registry("
    )

    assert merge_call_index < deterministic_application_index

    helper_start = orchestrator_source.index(
        "async def _persist_registry_merge_advice_for_section("
    )
    helper_end = orchestrator_source.index(
        "def _registry_merge_match_context(",
        helper_start,
    )
    helper_source = orchestrator_source[helper_start:helper_end]

    assert "generate_registry_updates(" in helper_source
    assert "persist_registry_merge_output(" in helper_source
    assert "ApplyRegistryFindingsCommand" not in helper_source
    assert "apply_findings_to_registry" not in helper_source


def test_deterministic_registry_application_remains_the_only_registry_mutator() -> None:
    registry_app_source = _read(REGISTRY_APP_SERVICE)
    registry_merge_service_source = _read(REGISTRY_MERGE_SERVICE)
    orchestrator_source = _read(ORCH)

    assert "RegistryUpdateAppliedBy.DETERMINISTIC_CODE" in registry_app_source
    assert "upsert_question_registry_entries" in registry_app_source
    assert "create_registry_update_applications" in registry_app_source

    assert "RegistryUpdateAppliedBy.LLM_ADVISORY" not in registry_app_source
    assert "RegistryUpdateAppliedBy.LLM_ADVISORY" not in registry_merge_service_source
    assert "RegistryUpdateAppliedBy.LLM_ADVISORY" not in orchestrator_source


def test_runtime_and_materialization_paths_do_not_read_advisory_proposals() -> None:
    runtime_paths = (
        Path(
            "src/application/services/faq_workbench_surface_materialization_service.py"
        ),
        Path("src/application/services/faq_workbench_runtime_publication_service.py"),
        Path("src/infrastructure/db/workbench_runtime_retrieval_repository.py"),
        Path("src/application/workbench/document_card_builder.py"),
        Path("src/application/workbench/document_card_projection.py"),
        Path("src/interfaces/composition/faq_workbench_surface_cards.py"),
    )

    for path in runtime_paths:
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        assert "registry_update_proposals" not in source, str(path)
        assert "RegistryUpdateProposal" not in source, str(path)
        assert "create_registry_update_proposals" not in source, str(path)
        assert "RegistryUpdateAppliedBy.LLM_ADVISORY" not in source, str(path)


def test_no_read_api_exists_for_advisory_registry_update_proposals_yet() -> None:
    port_source = _read(WORKBENCH_PORT)
    repo_source = _read(WORKBENCH_REPO)

    assert "create_registry_update_proposals" in port_source
    assert "create_registry_update_proposals" in repo_source

    forbidden_read_api_markers = (
        "list_registry_update_proposals",
        "get_registry_update_proposal",
        "load_registry_update_proposals",
        "select_registry_update_proposals",
    )

    for marker in forbidden_read_api_markers:
        assert marker not in port_source
        assert marker not in repo_source
