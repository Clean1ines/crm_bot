import inspect

from src.domain.project_plane.knowledge_retrieval_surface import (
    RUNTIME_ENTRY_KIND_VALUES,
)
from src.infrastructure.db.repositories.knowledge_repository import (
    ANSWERABLE_KNOWLEDGE_ENTRY_KINDS,
    KnowledgeRepository,
)
from src.infrastructure.db.repositories.rag_eval_repository import (
    RAG_EVAL_SOURCE_ENTRY_KINDS,
    RagEvalRepository,
)


def _old_entry_column_sql() -> str:
    return "kb." + "entry" + "_" + "type"


def _old_answer_role_value() -> str:
    return "answer" + "_knowledge"


def _old_chunk_value() -> str:
    return "ch" + "unk"


def _old_faq_mode_value() -> str:
    return "f" + "aq"


def _old_price_mode_value() -> str:
    return "price" + "_list"


def _old_instruction_mode_value() -> str:
    return "instruc" + "tion"


def _old_internal_eval_value() -> str:
    return "internal" + "_eval" + "_test"


def _old_negative_test_value() -> str:
    return "negative" + "_test"


def _old_retrieval_guideline_value() -> str:
    return "retrieval" + "_guideline"


def test_repository_runtime_entry_kinds_are_canonical_surface() -> None:
    assert ANSWERABLE_KNOWLEDGE_ENTRY_KINDS == tuple(sorted(RUNTIME_ENTRY_KIND_VALUES))
    assert RAG_EVAL_SOURCE_ENTRY_KINDS == tuple(sorted(RUNTIME_ENTRY_KIND_VALUES))

    for old_value in (
        _old_chunk_value(),
        _old_answer_role_value(),
        _old_faq_mode_value(),
        _old_price_mode_value(),
        _old_instruction_mode_value(),
        _old_internal_eval_value(),
        _old_negative_test_value(),
        _old_retrieval_guideline_value(),
    ):
        assert old_value not in ANSWERABLE_KNOWLEDGE_ENTRY_KINDS
        assert old_value not in RAG_EVAL_SOURCE_ENTRY_KINDS


def test_knowledge_repository_filters_by_entry_kind_not_old_column() -> None:
    source = inspect.getsource(KnowledgeRepository.search)
    source += inspect.getsource(KnowledgeRepository.preview_search)

    assert "knowledge_retrieval_surface AS rs" in source
    assert "rs.entry_kind = ANY" in source
    assert "rs.status = 'published'" in source
    assert "rs.visibility = 'runtime'" in source
    assert "kb.entry_kind = ANY" not in source
    assert "entry_type" not in source


def test_rag_eval_repository_filters_by_entry_kind_not_old_column() -> None:
    source = inspect.getsource(RagEvalRepository.load_document_entries)

    assert "knowledge_retrieval_surface AS rs" in source
    assert "rs.entry_kind = ANY" in source
    assert "rs.status = 'published'" in source
    assert "rs.visibility = 'runtime'" in source
    assert "kb.entry_kind = ANY" not in source
    assert "entry_type" not in source
