from pathlib import Path


THIS_FILE = Path(__file__).resolve()

CHECKED_ROOTS = (
    Path("src"),
    Path("tests/application"),
    Path("tests/architecture"),
    Path("tests/infrastructure"),
    Path("tests/integration"),
)

FORBIDDEN_IMPORT_TOKENS = (
    "src.application.workbench_observability.surface_cards",
    "workbench_observability.surface_cards",
)


def test_deleted_surface_cards_read_side_is_not_imported_by_active_code() -> None:
    chunks: list[str] = []
    for root in CHECKED_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if path.resolve() == THIS_FILE:
                continue
            if "__pycache__" in path.parts:
                continue
            if "_retired_legacy" in path.parts:
                continue
            chunks.append(path.read_text(encoding="utf-8"))

    source = "\n".join(chunks)

    for token in FORBIDDEN_IMPORT_TOKENS:
        assert token not in source
