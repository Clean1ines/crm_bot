from pathlib import Path


HTTP_FACING_OBSERVABILITY = Path(
    "src/infrastructure/db/workbench_observability_repository.py"
)

FORBIDDEN_SQL_PATTERNS = (
    "FROM knowledge_workbench_surfaces",
    "JOIN knowledge_workbench_surfaces",
    "UPDATE knowledge_workbench_surfaces",
    "INSERT INTO knowledge_workbench_surfaces",
    "DELETE FROM knowledge_workbench_surfaces",
)


def test_workbench_http_observability_does_not_query_retired_surfaces_table() -> None:
    source = HTTP_FACING_OBSERVABILITY.read_text(encoding="utf-8")
    offenders = [pattern for pattern in FORBIDDEN_SQL_PATTERNS if pattern in source]

    assert not offenders, "\n".join(offenders)
