from __future__ import annotations

from pathlib import Path


def test_curation_workspace_status_migration_allows_needs_republish() -> None:
    sql = " ".join(
        Path("migrations/118_allow_curation_workspace_needs_republish.sql")
        .read_text(encoding="utf-8")
        .lower()
        .split()
    )

    assert "drop constraint if exists draft_claim_curation_workspaces_status_check" in sql
    assert "status in ('draft', 'needs_republish', 'published')" in sql
