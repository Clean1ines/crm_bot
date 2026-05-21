from __future__ import annotations

from pathlib import Path


def test_answer_candidate_persistence_module_owns_candidate_write_sql() -> None:
    helper_source = Path(
        "src/infrastructure/db/repositories/knowledge_answer_candidate_persistence.py"
    ).read_text(encoding="utf-8")

    assert "DELETE FROM knowledge_answer_candidates" in helper_source
    assert "INSERT INTO knowledge_answer_candidates" in helper_source
    assert "INSERT INTO knowledge_candidate_clusters" in helper_source
    assert "DELETE FROM knowledge_candidate_cluster_members" in helper_source
    assert "INSERT INTO knowledge_candidate_cluster_members" in helper_source


def test_repository_delegates_answer_candidate_write_sql() -> None:
    repository_source = Path(
        "src/infrastructure/db/repositories/knowledge_repository.py"
    ).read_text(encoding="utf-8")

    assert "await persist_delete_raw_answer_candidates_for_batch(" in repository_source
    assert "await upsert_answer_candidates(" in repository_source
    assert "await upsert_candidate_clusters(" in repository_source

    assert "DELETE FROM knowledge_answer_candidates" not in repository_source
    assert "INSERT INTO knowledge_answer_candidates" not in repository_source
    assert "INSERT INTO knowledge_candidate_clusters" not in repository_source
    assert "DELETE FROM knowledge_candidate_cluster_members" not in repository_source
    assert "INSERT INTO knowledge_candidate_cluster_members" not in repository_source
