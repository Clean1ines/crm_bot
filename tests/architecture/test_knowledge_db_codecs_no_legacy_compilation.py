from __future__ import annotations

import importlib
from pathlib import Path


def test_knowledge_db_codecs_do_not_import_legacy_compilation_domain() -> None:
    source = Path(
        "src/infrastructure/db/repositories/knowledge_db_codecs.py"
    ).read_text(encoding="utf-8")

    forbidden = (
        "knowledge_compilation",
        "CanonicalKnowledgeEntry",
        "SourceChunk",
        "AnswerCandidate",
        "CandidateCluster",
        "CompilerRun",
    )
    for marker in forbidden:
        assert marker not in source


def test_knowledge_db_codecs_and_repository_import_without_legacy_compilation() -> None:
    for module in (
        "src.infrastructure.db.repositories.knowledge_db_codecs",
        "src.infrastructure.db.repositories.knowledge_repository",
    ):
        importlib.import_module(module)


def test_knowledge_db_codecs_tests_do_not_import_legacy_source_ref() -> None:
    source = Path("tests/database/repositories/test_knowledge_db_codecs.py").read_text(
        encoding="utf-8"
    )

    assert "src.domain.project_plane." + "knowledge_compilation" not in source
    assert "SourceRefView" in source
