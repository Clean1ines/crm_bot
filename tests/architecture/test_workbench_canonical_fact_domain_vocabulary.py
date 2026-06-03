from pathlib import Path


CHECKED = (
    Path("src/domain/project_plane/knowledge_workbench/registry.py"),
    Path("src/domain/project_plane/knowledge_workbench/__init__.py"),
    Path("src/application/ports/faq_workbench_registry_merge_generator.py"),
    Path("src/application/ports/faq_workbench_final_reconciliation_generator.py"),
    Path("src/infrastructure/llm/faq_workbench_final_reconciliation_generator.py"),
)

FORBIDDEN = (
    "QuestionRegistryEntry",
    "RegistryEntryStatus",
    "registry_entry_id",
    "registry_entry_key",
    "target_registry_entry_id",
)

REQUIRED = (
    "CanonicalFact",
    "CanonicalFactStatus",
    "fact_id",
    "fact_key",
    "target_fact_id",
)


def test_registry_domain_uses_canonical_fact_vocabulary() -> None:
    source = "\n".join(path.read_text(encoding="utf-8") for path in CHECKED)

    for token in REQUIRED:
        assert token in source

    for token in FORBIDDEN:
        assert token not in source
