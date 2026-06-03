from pathlib import Path


REPOSITORY = Path("src/infrastructure/db/knowledge_workbench_repository.py")
OBSERVABILITY_REPOSITORY = Path(
    "src/infrastructure/db/workbench_observability_repository.py"
)


def test_claim_observations_are_not_persisted_as_dedicated_rows() -> None:
    combined = "\n".join(
        (
            REPOSITORY.read_text(encoding="utf-8"),
            OBSERVABILITY_REPOSITORY.read_text(encoding="utf-8"),
        )
    )

    assert "knowledge_workbench_claim_observations" not in combined
    assert "knowledge_workbench_section_findings" not in combined
    assert "FROM knowledge_workbench_claim_observations" not in combined
    assert "INSERT INTO knowledge_workbench_claim_observations" not in combined
