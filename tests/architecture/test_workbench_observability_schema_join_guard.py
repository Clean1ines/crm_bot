from pathlib import Path


OBSERVABILITY_REPOSITORY = Path(
    "src/infrastructure/db/workbench_observability_repository.py"
)


def _method(source: str, name: str, next_name: str) -> str:
    start = source.index(f"async def {name}(")
    end = source.index(f"async def {next_name}(", start)
    return source[start:end]


def test_workbench_observability_does_not_join_fact_mentions_by_nonexistent_columns() -> (
    None
):
    source = OBSERVABILITY_REPOSITORY.read_text(encoding="utf-8")

    assert "m.project_id = f.project_id" not in source
    assert "m.document_id = f.document_id" not in source


def test_evidence_trace_surfaces_uses_fact_mentions_registry_fact_join() -> None:
    source = OBSERVABILITY_REPOSITORY.read_text(encoding="utf-8")
    method = _method(
        source,
        "list_evidence_trace_surfaces",
        "list_workbench_documents",
    )

    assert "LEFT JOIN knowledge_workbench_fact_mentions AS m" in method
    assert "ON m.fact_id = f.fact_id" in method
    assert "AND m.registry_id = f.registry_id" in method
    assert "m.project_id" not in method
    assert "m.document_id" not in method


def test_import_quality_surfaces_uses_fact_mentions_registry_fact_join() -> None:
    source = OBSERVABILITY_REPOSITORY.read_text(encoding="utf-8")
    method = _method(
        source,
        "list_import_quality_surfaces",
        "list_import_quality_node_runs",
    )

    assert "LEFT JOIN knowledge_workbench_fact_mentions AS m" in method
    assert "ON m.fact_id = f.fact_id" in method
    assert "AND m.registry_id = f.registry_id" in method
    assert "m.project_id" not in method
    assert "m.document_id" not in method
