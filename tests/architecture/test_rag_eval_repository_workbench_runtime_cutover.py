from __future__ import annotations

import importlib
import inspect
from pathlib import Path

from src.infrastructure.db.repositories.rag_eval_repository import (
    _source_ref_views_from_payload,
)


def test_rag_eval_repository_loads_eval_sources_from_workbench_runtime_entries() -> (
    None
):
    source = Path(
        "src/infrastructure/db/repositories/rag_eval_repository.py"
    ).read_text(encoding="utf-8")

    assert "knowledge_workbench_runtime_retrieval_entries AS re" in source
    assert "JOIN knowledge_workbench_surfaces AS s" in source
    assert "re.status = 'published'" in source
    assert "re.visibility = 'runtime'" in source
    assert "knowledge_retrieval_surface" not in source
    assert "RUNTIME_ENTRY_KIND_VALUES" not in source


def test_rag_eval_repository_imports_without_legacy_retrieval_surface() -> None:
    module = importlib.import_module(
        "src.infrastructure.db.repositories.rag_eval_repository"
    )

    assert hasattr(module, "RagEvalRepository")


def test_rag_eval_source_refs_accept_workbench_string_refs() -> None:
    refs = _source_ref_views_from_payload(
        ["document-1#section-0001", "  quoted evidence  "]
    )

    assert tuple(ref.quote for ref in refs) == (
        "document-1#section-0001",
        "quoted evidence",
    )
    assert tuple(ref.source_index for ref in refs) == (0, 1)


def test_rag_eval_repository_source_has_no_old_compiler_vocab() -> None:
    source = inspect.getsource(
        importlib.import_module(
            "src.infrastructure.db.repositories.rag_eval_repository"
        )
    )

    forbidden = (
        "knowledge_retrieval_surface",
        "knowledge_compilation",
        "CanonicalKnowledgeEntry",
        "AnswerCandidate",
        "CandidateCluster",
        "CompilerRun",
        "CompilerBatch",
        "SourceChunk",
    )
    for marker in forbidden:
        assert marker not in source
