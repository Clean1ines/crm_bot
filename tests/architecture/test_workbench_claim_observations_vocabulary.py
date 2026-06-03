from pathlib import Path


CHECKED_ROOTS = (
    Path("src/application"),
    Path("src/domain/project_plane/knowledge_workbench"),
    Path("src/infrastructure"),
    Path("src/interfaces"),
)

FORBIDDEN_TOKENS = (
    "SectionFindings",
    "section_findings",
    "section findings",
    "section finding",
    "faq_surface_section_findings",
    "workbench_section_findings",
)

REQUIRED_TOKENS = (
    "ClaimObservations",
    "claim_observations",
)


def _source() -> str:
    chunks: list[str] = []
    for root in CHECKED_ROOTS:
        if not root.exists():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix not in {".py", ".txt", ".md"}:
                continue
            chunks.append(path.read_text(encoding="utf-8"))
    return "\n".join(chunks)


def test_workbench_uses_claim_observations_not_section_findings_vocabulary() -> None:
    source = _source()

    for token in REQUIRED_TOKENS:
        assert token in source

    offenders = [token for token in FORBIDDEN_TOKENS if token in source]
    assert not offenders, "\n".join(offenders)
