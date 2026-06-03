from pathlib import Path


CHECKED = (
    Path("src/infrastructure/db/workbench_observability_repository.py"),
    Path("src/application/workbench_observability"),
    Path("src/interfaces/composition"),
    Path("src/interfaces/http/knowledge.py"),
)

FORBIDDEN = (
    "surface_cards",
    "get_surface_cards_document",
    "list_workbench_surface_cards",
)


def test_surface_cards_read_side_is_removed_from_production() -> None:
    chunks: list[str] = []
    for path in CHECKED:
        if not path.exists():
            continue
        if path.is_file():
            chunks.append(path.read_text(encoding="utf-8"))
        else:
            for child in path.rglob("*.py"):
                if "__pycache__" in child.parts:
                    continue
                chunks.append(child.read_text(encoding="utf-8"))

    source = "\n".join(chunks)

    for token in FORBIDDEN:
        assert token not in source
