from __future__ import annotations

from pathlib import Path


LIVE_FILES = (
    Path("src/infrastructure/db/repositories/knowledge_repository.py"),
    Path("src/infrastructure/db/repositories/knowledge_search_queries.py"),
    Path("src/infrastructure/db/repositories/knowledge_search_ranking.py"),
    Path("src/domain/project_plane/production_retrieval.py"),
    Path("src/domain/project_plane/rag_eval_retrieval.py"),
)


FORBIDDEN = (
    "knowledge_" + "retrieval_" + "surface",
    "rs." + "answer AS content",
    "retrieval_" + "surface_lexical",
    "rs." + "enrichment",
    "rs." + "search_text",
)


def test_production_retrieval_live_code_does_not_reference_legacy_runtime_table() -> (
    None
):
    offenders: list[str] = []

    for path in LIVE_FILES:
        text = path.read_text(encoding="utf-8")
        for token in FORBIDDEN:
            if token in text:
                offenders.append(f"{path.as_posix()}: {token}")

    assert offenders == []


def test_production_search_sql_uses_workbench_runtime_tables() -> None:
    source = Path(
        "src/infrastructure/db/repositories/knowledge_search_queries.py"
    ).read_text(encoding="utf-8")

    assert "knowledge_workbench_runtime_retrieval_entries" in source
    assert "knowledge_workbench_runtime_retrieval_entry_embeddings" in source
    assert "knowledge_workbench_canonical_facts" in source
    assert "entry.claim AS content" in source
    assert "entry.possible_questions AS questions" in source
    assert "entry.source_refs->'source_claim_refs' AS source_refs" in source
