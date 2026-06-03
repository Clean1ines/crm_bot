from pathlib import Path


CHECKED = (
    Path("src/application/ports/knowledge_workbench.py"),
    Path("src/application/services/faq_workbench_section_work_item_processor_service.py"),
    Path("src/application/ports/faq_workbench_registry_merge_generator.py"),
    Path("src/application/ports/faq_workbench_final_reconciliation_generator.py"),
)

FORBIDDEN = (
    "QuestionRegistryEntry",
    "list_question_registry_entries",
    "upsert_question_registry_entries",
    "registry_entries",
    "registry_entry_id",
    "registry_entry_key",
    "target_registry_entry_id",
)

REQUIRED = (
    "CanonicalFact",
    "list_canonical_facts",
    "upsert_canonical_facts",
    "canonical_facts",
)


def test_workbench_application_uses_canonical_fact_method_vocabulary() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in CHECKED)

    for token in REQUIRED:
        assert token in source

    for token in FORBIDDEN:
        assert token not in source
