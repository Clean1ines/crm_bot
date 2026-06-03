from pathlib import Path


THIS_FILE = Path(__file__).resolve()

# This guard intentionally checks production code only.
# There are still old tests/helpers being retired separately; this guard must not
# fail because of test archives while the production path is being cut over.
CHECKED_ROOTS = (
    Path("src/application"),
    Path("src/domain/project_plane/knowledge_workbench"),
    Path("src/interfaces"),
)

FORBIDDEN = (
    "KnowledgeSurface",
    "ParsedSectionFinding",
    "SurfaceMaterialization",
    "surface_cards",
)

# Keep surface_materialization out of this guard for now because the enum value
# still exists in nodes/retention policy as historical process vocabulary.
# A separate node/retention cutover should decide whether to delete/rename it.


def test_deleted_workbench_surface_contracts_are_not_imported_by_production_code() -> None:
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

    offenders = [token for token in FORBIDDEN if token in source]
    assert not offenders, "\\n".join(offenders)
