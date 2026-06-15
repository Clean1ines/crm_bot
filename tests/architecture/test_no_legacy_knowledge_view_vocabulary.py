from __future__ import annotations

from pathlib import Path


LIVE_FILES = (
    Path("src/domain/project_plane/knowledge_views.py"),
    Path("src/infrastructure/db/repositories/knowledge_document_queries.py"),
    Path("src/infrastructure/db/repositories/knowledge_db_codecs.py"),
    Path("frontend/src/shared/api/modules/knowledge.ts"),
)


FRONTEND_KNOWLEDGE_FILES = tuple(Path("frontend/src/pages/knowledge").rglob("*.tsx"))


FORBIDDEN_LIVE_TOKENS = (
    "knowledge_" + "entries",
    "knowledge_" + "retrieval_" + "surface",
    "knowledge_" + "source_" + "chunks",
    "source_" + "chunk_id",
    "chunk_" + "count",
    "structured_" + "entries",
    "structured_" + "chunk_" + "count",
    "Knowledge" + "CompilerBatchView",
    "Knowledge" + "AnswerCandidateSummaryView",
)


def test_live_knowledge_view_files_do_not_expose_legacy_vocabulary() -> None:
    offenders: list[str] = []

    for path in LIVE_FILES:
        source = path.read_text(encoding="utf-8")
        for token in FORBIDDEN_LIVE_TOKENS:
            if token in source:
                offenders.append(f"{path.as_posix()}: {token}")

    assert offenders == []


def test_frontend_knowledge_pages_do_not_use_legacy_document_view_vocabulary() -> None:
    offenders: list[str] = []

    for path in FRONTEND_KNOWLEDGE_FILES:
        source = path.read_text(encoding="utf-8")
        for token in (
            "source_" + "chunk_id",
            "chunk_" + "count",
            "structured_" + "entries",
            "structured_" + "chunk_" + "count",
            "retrieval_" + "surface",
        ):
            if token in source:
                offenders.append(f"{path.as_posix()}: {token}")

    assert offenders == []


def test_workbench_document_view_counter_names_are_explicit() -> None:
    source = Path("src/domain/project_plane/knowledge_views.py").read_text(
        encoding="utf-8"
    )

    required = (
        "source_unit_count",
        "draft_claim_count",
        "draft_claim_embedding_count",
        "curated_item_count",
        "runtime_entry_count",
        "runtime_embedding_count",
        "publication_count",
    )
    for token in required:
        assert token in source
