from pathlib import Path


CHECKED_ROOTS = (
    Path("src/application"),
    Path("src/infrastructure"),
    Path("src/domain/project_plane/knowledge_workbench"),
)

ACTIVE_MIGRATIONS = tuple(Path("migrations").glob("*.sql"))

FORBIDDEN_TABLE_TOKENS = (
    "knowledge_workbench_claim_observations",
    "knowledge_workbench_section_findings",
)

REQUIRED_ARTIFACT_TOKENS = (
    "ProcessingNodeArtifactType.PARSED_LLM_OUTPUT",
    'payload.get("claim_observations")',
    "claim_observations=tuple(generation_result.claim_observations)",
)


def _production_source() -> str:
    chunks: list[str] = []
    for root in CHECKED_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*.py")):
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def _active_migration_source() -> str:
    return "\n".join(path.read_text(encoding="utf-8") for path in ACTIVE_MIGRATIONS)


def test_claim_observations_are_not_backed_by_dedicated_table() -> None:
    combined = _production_source() + "\n" + _active_migration_source()

    for token in FORBIDDEN_TABLE_TOKENS:
        assert token not in combined


def test_claim_observations_flow_is_artifact_first() -> None:
    source = _production_source()

    for token in REQUIRED_ARTIFACT_TOKENS:
        assert token in source
