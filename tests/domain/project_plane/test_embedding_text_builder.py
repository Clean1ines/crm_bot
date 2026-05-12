from src.domain.project_plane.embedding_text import (
    CANONICAL_EMBEDDING_TEXT_VERSION,
    build_canonical_entry_embedding_text,
    build_retrieval_surface_search_text,
)
from src.domain.project_plane.knowledge_compilation import (
    CanonicalKnowledgeEntry,
    EmbeddingText,
    KnowledgeEnrichment,
    KnowledgeEntryKind,
    KnowledgeEntryStatus,
    KnowledgeEntryVisibility,
    SourceRef,
)


def _entry() -> CanonicalKnowledgeEntry:
    return CanonicalKnowledgeEntry(
        id="entry-1",
        project_id="project-1",
        document_id="document-1",
        compiler_run_id="run-1",
        stable_key="stable-key",
        entry_kind=KnowledgeEntryKind.FAQ_ANSWER,
        title="Подключение",
        answer="Подключение занимает один рабочий день.",
        source_refs=(
            SourceRef(source_index=0, quote="Подключение занимает один рабочий день."),
        ),
        enrichment=KnowledgeEnrichment(
            questions=("Сколько занимает подключение?",),
            paraphrases=("Когда запустят проект?",),
            synonyms=("онбординг",),
            typo_queries=("падключение",),
            colloquial_queries=("когда стартуем",),
            tags=("подключение",),
            retrieval_guards=("не отвечать про возврат",),
        ),
        embedding_text=EmbeddingText(
            value="legacy llm supplied embedding text must be ignored",
            version="legacy",
        ),
        status=KnowledgeEntryStatus.PUBLISHED,
        visibility=KnowledgeEntryVisibility.RUNTIME,
        version=1,
        compiler_version="test",
        embedding_text_version="legacy",
    )


def test_builder_is_the_single_authoritative_source_for_entry_embedding_text() -> None:
    text = build_canonical_entry_embedding_text(_entry())

    assert text.version == CANONICAL_EMBEDDING_TEXT_VERSION
    assert "Подключение" in text.value
    assert "Подключение занимает один рабочий день." in text.value
    assert "Сколько занимает подключение?" in text.value
    assert "Когда запустят проект?" in text.value
    assert "онбординг" in text.value
    assert "падключение" in text.value
    assert "когда стартуем" in text.value
    assert "legacy llm supplied embedding text must be ignored" not in text.value
    assert "не отвечать про возврат" not in text.value


def test_retrieval_surface_search_text_uses_answer_and_positive_embedding_surface() -> (
    None
):
    search_text = build_retrieval_surface_search_text(_entry())

    assert "Подключение занимает один рабочий день." in search_text
    assert "Сколько занимает подключение?" in search_text
    assert "не отвечать про возврат" not in search_text
