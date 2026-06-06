from pathlib import Path
import re


OBSERVABILITY_REPOSITORY = Path(
    "src/infrastructure/db/workbench_observability_repository.py"
)


def _method(source: str, name: str) -> str:
    start = source.index(f"async def {name}(")

    next_method = re.search(
        r"\n    async def [A-Za-z_][A-Za-z0-9_]*\(",
        source[start + 1 :],
    )
    if next_method is None:
        return source[start:]

    end = start + 1 + next_method.start()
    return source[start:end]


def test_import_quality_node_runs_uses_real_error_columns() -> None:
    source = OBSERVABILITY_REPOSITORY.read_text(encoding="utf-8")
    method = _method(source, "list_import_quality_node_runs")

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
