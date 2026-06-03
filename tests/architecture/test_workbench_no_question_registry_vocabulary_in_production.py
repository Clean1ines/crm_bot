from pathlib import Path


CHECKED_ROOTS = (
    Path("src/application"),
    Path("src/domain/project_plane/knowledge_workbench"),
    Path("src/infrastructure"),
    Path("src/interfaces"),
)

FORBIDDEN = (
    "QuestionRegistry",
    "QuestionRegistryStatus",
    "QuestionRegistryEntry",
    "question_registry",
    "final_question_registry",
    "create_question_registry",
    "get_question_registry_for_run",
    "list_question_registry_entries",
    "upsert_question_registry_entries",
)


def test_question_registry_vocabulary_is_not_used_in_production() -> None:
    chunks: list[str] = []
    for root in CHECKED_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            chunks.append(path.read_text(encoding="utf-8"))

    source = "\n".join(chunks)

    for token in FORBIDDEN:
        assert token not in source
