from pathlib import Path


CHECKED = (
    Path("src/application/workbench/document_card_projection.py"),
    Path("src/application/workbench/document_card_builder.py"),
    Path("src/application/workbench/document_card_contract.py"),
    Path("src/application/workbench/dto.py"),
    Path("src/infrastructure/db/workbench_observability_repository.py"),
)


def test_document_card_uses_canonical_fact_count_not_registry_entry_count() -> None:
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in CHECKED
        if path.exists()
    )

    assert "canonical_fact_count" in source
    assert "registry_entry_count" not in source
