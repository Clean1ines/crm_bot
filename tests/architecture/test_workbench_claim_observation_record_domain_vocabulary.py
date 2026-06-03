from pathlib import Path


THIS_FILE = Path(__file__).resolve()

CHECKED = (
    Path("src/domain/project_plane/knowledge_workbench/registry.py"),
    Path("src/domain/project_plane/knowledge_workbench/shared.py"),
    Path("src/domain/project_plane/knowledge_workbench/__init__.py"),
    Path("src/domain/project_plane/knowledge_workbench/registry_application_queue.py"),
    Path("src/application/ports/knowledge_workbench.py"),
)

FORBIDDEN = (
    "SectionFinding",
    "SectionFindingAction",
    "SectionFindingStatus",
    "FindingId",
    "finding_id",
    "source_finding_id",
    "findings: tuple[",
)

REQUIRED = (
    "ClaimObservationRecord",
    "ClaimObservationAction",
    "ClaimObservationStatus",
    "ClaimObservationId",
    "claim_observation_id",
    "source_claim_observation_id",
)


def test_workbench_registry_domain_uses_claim_observation_record_vocabulary() -> None:
    chunks: list[str] = []
    for path in CHECKED:
        if not path.exists():
            continue
        if path.resolve() == THIS_FILE:
            continue
        chunks.append(path.read_text(encoding="utf-8"))

    source = "\n".join(chunks)

    for token in REQUIRED:
        assert token in source

    for token in FORBIDDEN:
        assert token not in source
