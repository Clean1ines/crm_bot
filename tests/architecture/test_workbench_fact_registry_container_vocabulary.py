from pathlib import Path


CHECKED = (
    Path("src/domain/project_plane/knowledge_workbench/registry.py"),
    Path("src/domain/project_plane/knowledge_workbench/__init__.py"),
    Path("src/application/ports/knowledge_workbench.py"),
    Path("src/application/ports/faq_workbench_registry_merge_generator.py"),
    Path("src/application/services/faq_workbench_fresh_upload_service.py"),
    Path("src/application/services/faq_workbench_section_work_item_processor_service.py"),
    Path("src/application/services/faq_workbench_registry_application_work_item_processor_service.py"),
    Path("src/application/services/faq_workbench_registry_merge_service.py"),
    Path("src/application/services/faq_workbench_claim_observations_service.py"),
    Path("src/application/services/faq_workbench_registry_application_service.py"),
    Path("src/application/workbench/processing_graph_contract.py"),
)

FORBIDDEN = (
    "QuestionRegistry",
    "QuestionRegistryStatus",
    "create_question_registry",
    "get_question_registry_for_run",
    "question_registry",
)

REQUIRED = (
    "FactRegistry",
    "FactRegistryStatus",
    "create_fact_registry",
    "get_fact_registry_for_run",
    "fact_registry",
)


def test_workbench_uses_fact_registry_container_vocabulary() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in CHECKED if path.exists())

    for token in REQUIRED:
        assert token in source

    for token in FORBIDDEN:
        assert token not in source
