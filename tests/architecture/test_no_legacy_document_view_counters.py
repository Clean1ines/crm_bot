from __future__ import annotations

from pathlib import Path


LIVE_FILES = (
    Path("src/infrastructure/db/repositories/knowledge_document_queries.py"),
    Path("src/domain/project_plane/knowledge_views.py"),
)


FRONTEND_FILES = (
    Path("frontend/src/pages/knowledge/KnowledgePage.tsx"),
    Path("frontend/src/pages/knowledge/components/KnowledgeDocumentCard.tsx"),
)


FORBIDDEN = (
    "knowledge_" + "entries",
    "knowledge_" + "retrieval_" + "surface",
    "knowledge_" + "source_" + "chunks",
)


def test_document_view_queries_do_not_reference_legacy_counter_tables() -> None:
    offenders: list[str] = []

    for path in LIVE_FILES:
        source = path.read_text(encoding="utf-8")
        for token in FORBIDDEN:
            if token in source:
                offenders.append(f"{path.as_posix()}: {token}")

    assert offenders == []


def test_frontend_knowledge_cards_do_not_name_legacy_retrieval_surface() -> None:
    offenders: list[str] = []

    for path in FRONTEND_FILES:
        if not path.exists():
            continue
        source = path.read_text(encoding="utf-8")
        if FORBIDDEN[1] in source:
            offenders.append(path.as_posix())

    assert offenders == []


def test_document_view_queries_count_workbench_runtime_state() -> None:
    source = Path(
        "src/infrastructure/db/repositories/knowledge_document_queries.py"
    ).read_text(encoding="utf-8")

    required = (
        "source_documents",
        "source_units",
        "draft_claim_observations",
        "draft_claim_embeddings",
        "draft_claim_curation_workspaces",
        "draft_claim_curation_items",
        "knowledge_workbench_runtime_retrieval_entries",
        "knowledge_workbench_runtime_retrieval_entry_embeddings",
        "knowledge_workbench_runtime_publications",
    )
    for token in required:
        assert token in source
