from __future__ import annotations

import io
import re
import tokenize
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]

# These DB column names are obsolete after migrations 076/077 and must not be
# referenced directly from production SQL.
#
# Important:
# - canonical_fact_count / fact_relation_count are still valid application-level
#   metric aliases and DTO fields.
# - The DB columns with those names were obsolete only on
#   knowledge_workbench_registry_snapshots.
# - Therefore this guard blocks actual legacy DB-column references, not every
#   business/output alias that happens to use the same vocabulary.
FORBIDDEN_SQL_SUBSTRINGS = (
    "fact_registry_id",
    "fact_registry_payload",
    "fact_registry_node_run_id",
    "fact_registry_application_queue_item_id",
)

# These are forbidden only as direct registry snapshot column references.
FORBIDDEN_REGISTRY_SNAPSHOT_COLUMNS = (
    "canonical_fact_count",
    "fact_relation_count",
)

SQL_HINTS = (
    "SELECT ",
    "INSERT ",
    "UPDATE ",
    "DELETE ",
    "FROM ",
    "JOIN ",
    "CREATE TABLE",
    "ALTER TABLE",
    "REFERENCES ",
)

SCAN_PATHS = (
    ROOT / "src",
)


def _python_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_PATHS:
        if not root.exists():
            continue
        files.extend(
            path
            for path in root.rglob("*.py")
            if "__pycache__" not in path.parts
        )
    return sorted(files)


def _sql_string_literals(path: Path) -> list[tuple[int, str]]:
    source = path.read_text(encoding="utf-8")
    result: list[tuple[int, str]] = []

    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.type != tokenize.STRING:
                continue

            raw = token.string
            upper = raw.upper()
            if any(hint in upper for hint in SQL_HINTS):
                result.append((token.start[0], raw))
    except tokenize.TokenError:
        result.append((1, source))

    return result


def _looks_like_registry_snapshot_legacy_count_reference(
    sql_literal: str,
    column_name: str,
) -> bool:
    # Direct old-column references after 076 are invalid:
    #
    #   knowledge_workbench_registry_snapshots.canonical_fact_count
    #   snapshot.canonical_fact_count
    #   snapshots.canonical_fact_count
    #   registry_snapshots.canonical_fact_count
    #
    # But these are valid output aliases/business metrics:
    #
    #   COUNT(f.fact_id)::int AS canonical_fact_count
    #   registry_summary.canonical_fact_count
    #   row.get("canonical_fact_count")
    direct_patterns = (
        rf"knowledge_workbench_registry_snapshots\s*\.\s*{column_name}",
        rf"\bsnapshot\s*\.\s*{column_name}",
        rf"\bsnapshots\s*\.\s*{column_name}",
        rf"\bregistry_snapshots\s*\.\s*{column_name}",
    )
    return any(
        re.search(pattern, sql_literal, flags=re.IGNORECASE)
        for pattern in direct_patterns
    )


def test_workbench_sql_does_not_use_legacy_076_077_column_names() -> None:
    hits: list[str] = []

    for path in _python_files():
        relative = path.relative_to(ROOT)
        for line_number, sql_literal in _sql_string_literals(path):
            for token in FORBIDDEN_SQL_SUBSTRINGS:
                if token in sql_literal:
                    hits.append(f"{relative}:{line_number}: {token}")

            for token in FORBIDDEN_REGISTRY_SNAPSHOT_COLUMNS:
                if _looks_like_registry_snapshot_legacy_count_reference(
                    sql_literal,
                    token,
                ):
                    hits.append(f"{relative}:{line_number}: {token}")

    assert hits == [], (
        "Workbench SQL still references legacy DB column names after 076/077:\n"
        + "\n".join(hits)
    )
