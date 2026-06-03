from pathlib import Path


REPOSITORY = Path("src/infrastructure/db/workbench_observability_repository.py")

FORBIDDEN_SQL_TOKENS = (
    "knowledge_workbench_question_registries",
    "knowledge_workbench_question_registry_entries",
)

REQUIRED_SQL_TOKENS = (
    "knowledge_workbench_fact_registries",
    "knowledge_workbench_canonical_facts",
    "knowledge_workbench_fact_mentions",
)


def test_workbench_observability_uses_fact_registry_schema_not_question_registry_tables() -> None:
    source = REPOSITORY.read_text(encoding="utf-8")

    for token in FORBIDDEN_SQL_TOKENS:
        assert token not in source

    for token in REQUIRED_SQL_TOKENS:
        assert token in source
