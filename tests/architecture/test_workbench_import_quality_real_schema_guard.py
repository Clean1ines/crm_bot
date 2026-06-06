from pathlib import Path


OBSERVABILITY_REPOSITORY = Path(
    "src/infrastructure/db/workbench_observability_repository.py"
)


def _method(source: str, name: str, next_name: str) -> str:
    start = source.index(f"async def {name}(")
    end = source.index(f"async def {next_name}(", start)
    return source[start:end]


def test_import_quality_node_runs_uses_real_error_columns() -> None:
    source = OBSERVABILITY_REPOSITORY.read_text(encoding="utf-8")
    method = _method(
        source,
        "list_import_quality_node_runs",
        "list_processing_overview_documents",
    )

    assert (
        "COALESCE(error_message_user, error_message_internal, '') AS error_message"
        in method
    )
    assert "                error_message,\n" not in method


def test_observability_does_not_use_known_missing_workbench_columns() -> None:
    source = OBSERVABILITY_REPOSITORY.read_text(encoding="utf-8")

    forbidden = (
        "m.project_id = f.project_id",
        "m.document_id = f.document_id",
        "f.canonical_label",
        "f.canonical_statement",
        "f.question_variants",
        "f.fact_kind",
    )

    for marker in forbidden:
        assert marker not in source
