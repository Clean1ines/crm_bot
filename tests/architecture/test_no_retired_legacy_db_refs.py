import re
from pathlib import Path


SCAN_ROOTS = (
    Path("src"),
    Path("frontend/src"),
    Path("tests"),
)

ALLOWED_FILES = {
    Path("tests/architecture/test_no_retired_legacy_db_refs.py"),
    Path("tests/architecture/test_retired_legacy_migrations_are_not_active.py"),
    Path("tests/architecture/test_no_legacy_rag_eval_surface.py"),
    Path("tests/architecture/test_retired_pipeline_artifacts_migration.py"),
    Path("tests/architecture/test_published_workbench_retrieval_boundary.py"),
    Path("tests/architecture/test_workbench_rag_eval_boundary.py"),
    Path(
        "tests/contexts/knowledge_workbench/retrieval/infrastructure/postgres/"
        "test_postgres_published_workbench_retrieval_repository.py",
    ),
    Path(
        "tests/contexts/knowledge_workbench/rag_eval/infrastructure/postgres/"
        "test_postgres_workbench_rag_eval_repository.py",
    ),
    Path("frontend/src/shared/api/core/errors.test.ts"),
}

FORBIDDEN_TOKENS = (
    "knowledge_retrieval_surface",
    "knowledge_entries",
    "knowledge_source_chunks",
    "knowledge_edit_actions",
    "rag_eval_datasets",
    "rag_eval_questions",
    "rag_eval_results",
    "rag_eval_review_groups",
    "rag_eval_jobs",
    "pipeline_artifacts",
    "knowledge_workbench_surfaces",
    "knowledge_workbench_surface_cards",
    "source_chunk_id",
)

# Current canonical Workbench RAG eval/publication code legitimately has answer_text
# fields. Do not ban answer_text globally; retired old rag_eval answer_text is covered
# by retired migration/table guards.


def test_live_code_does_not_reference_retired_legacy_db_tables() -> None:
    offenders: list[str] = []

    for root in SCAN_ROOTS:
        if not root.exists():
            continue

        for path in sorted(root.rglob("*")):
            if path in ALLOWED_FILES:
                continue
            if path.is_dir() or path.suffix not in {".py", ".ts", ".tsx", ".sql"}:
                continue

            source = path.read_text(encoding="utf-8")
            for token in FORBIDDEN_TOKENS:
                pattern = rf"(?<![A-Za-z0-9_]){re.escape(token)}(?![A-Za-z0-9_])"
                if re.search(pattern, source):
                    offenders.append(f"{path}: {token}")

    assert offenders == []


def test_retired_legacy_directory_is_not_scanned_as_active_migrations() -> None:
    retired = Path("migrations/_retired_legacy")
    assert retired.is_dir()

    active_sql = {path.name for path in Path("migrations").glob("*.sql")}
    retired_sql = {path.name for path in retired.glob("*.sql")}

    assert active_sql.isdisjoint(
        {
            "055_create_rag_eval.sql",
            "058_create_knowledge_source_chunks.sql",
            "059_create_knowledge_entries_and_retrieval_surface.sql",
        },
    )
    assert {
        "055_create_rag_eval.sql",
        "058_create_knowledge_source_chunks.sql",
        "059_create_knowledge_entries_and_retrieval_surface.sql",
    } <= retired_sql
