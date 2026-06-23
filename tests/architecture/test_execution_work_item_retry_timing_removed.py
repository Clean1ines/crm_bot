from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN_CANONICAL_ROOTS = (
    ROOT / "src" / "contexts" / "execution_runtime",
    ROOT / "src" / "interfaces" / "composition",
    ROOT / "migrations",
    ROOT / "tests" / "contexts" / "execution_runtime",
    ROOT / "tests" / "interfaces" / "composition",
)

ALLOWED_RETRY_TIMER_REMOVAL_MIGRATIONS = frozenset(
    {
        "098_drop_execution_work_item_next_attempt_at.sql",
        "099_drop_legacy_execution_queue_next_attempt_at.sql",
    }
)


def _text_files(root: Path) -> tuple[Path, ...]:
    if not root.exists():
        return ()
    return tuple(
        path
        for path in root.rglob("*")
        if path.is_file()
        and path.suffix in {".py", ".sql", ".md", ".txt"}
        and ".git" not in path.parts
    )


def test_execution_work_item_canonical_code_does_not_mention_removed_retry_timer() -> (
    None
):
    offenders: list[str] = []
    for root in FORBIDDEN_CANONICAL_ROOTS:
        for file_path in _text_files(root):
            text = file_path.read_text(encoding="utf-8")
            if file_path.name in ALLOWED_RETRY_TIMER_REMOVAL_MIGRATIONS:
                continue
            if "next_attempt_at" in text:
                offenders.append(str(file_path.relative_to(ROOT)))

    assert offenders == []


def test_work_item_admission_queries_do_not_filter_by_time() -> None:
    lease_repo = (
        ROOT
        / "src"
        / "contexts"
        / "execution_runtime"
        / "infrastructure"
        / "postgres"
        / "postgres_work_item_lease_repository.py"
    ).read_text(encoding="utf-8")

    forbidden_fragments = (
        "wi.next_attempt_at",
        "available_at",
        "deferred_until",
        "not_before",
    )

    for fragment in forbidden_fragments:
        assert fragment not in lease_repo
