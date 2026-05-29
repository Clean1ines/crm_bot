from __future__ import annotations

from src.application.services import knowledge_answer_resolution_service as ars
from src.application.services import knowledge_compiled_entry_cleanup as cleanup_helpers
from src.application.services import knowledge_retighten_planner as retighten_helpers
from src.domain.project_plane.knowledge_preprocessing import KnowledgePreprocessingEntry


def _product_positioning_entries() -> tuple[KnowledgePreprocessingEntry, ...]:
    return (
        KnowledgePreprocessingEntry(
            title="Итоговое позиционирование продукта",
            answer=(
                "Система превращает документы бизнеса в управляемую AI-базу знаний, "
                "проверяет качество поиска и подключает готовые знания к клиентскому ассистенту. "
                "Ещё короче: Мастерская знаний для AI-ассистентов бизнеса. "
                "Продукт — это платформа управления AI-базами знаний для бизнеса. "
                "Она помогает загрузить документы, извлечь знания, проверить получившиеся фрагменты, "
                "убрать мусор и дубли, слить похожие ответы, улучшить поисковую поверхность, "
                "проверить качество retrieval, использовать готовую базу знаний в Telegram-ассистенте, "
                "передавать сложные обращения менеджерам, работать с клиентами через веб-панель. "
                "Главная ценность: бизнес получает AI-ассистента, которому можно больше доверять, "
                "потому что его знания можно видеть, проверять, исправлять и улучшать. "
                "Самая короткая формула: Платформа, которая превращает документы бизнеса "
                "в проверяемую AI-базу знаний и подключает её к клиентскому ассистенту."
            ),
            source_excerpt="Продукт — это платформа управления AI-базами знаний для бизнеса.",
            questions=(
                "Что это за продукт?",
                "Как позиционируется продукт?",
                "Что делает платформа?",
            ),
            synonyms=(),
            tags=(),
            embedding_text="",
            canonical_question="Что это за продукт?",
        ),
        KnowledgePreprocessingEntry(
            title="Короткий ответ о продукте",
            answer=(
                "Продукт объединяет базу знаний, инструменты проверки качества, "
                "AI-ассистента, Telegram-бота и веб-панель для команды."
            ),
            source_excerpt=(
                "Продукт объединяет базу знаний, инструменты проверки качества, "
                "AI-ассистента, Telegram-бота и веб-панель."
            ),
            questions=(
                "Что входит в продукт?",
                "Что объединяет продукт?",
                "Коротко, что это?",
            ),
            synonyms=(),
            tags=(),
            embedding_text="",
            canonical_question="Коротко, что это за продукт?",
        ),
        KnowledgePreprocessingEntry(
            title="Что это за продукт",
            answer=(
                "Это платформа управления AI-базами знаний. Она помогает загрузить документы, "
                "превратить их в проверяемые знания, проверить качество поиска и использовать "
                "готовую базу в клиентском Telegram-ассистенте."
            ),
            source_excerpt="Это платформа управления AI-базами знаний.",
            questions=(
                "Что это за продукт?",
                "Для чего нужна платформа?",
                "Что делает система?",
            ),
            synonyms=(),
            tags=(),
            embedding_text="",
            canonical_question="Что это за продукт?",
        ),
    )


def test_same_intent_summary_candidates_form_cluster_before_cleanup() -> None:
    cases = ars._answer_resolution_cases_from_entries(_product_positioning_entries())

    assert len(cases) == 1
    assert len(cases[0].candidates) == 3


def test_same_intent_summary_survives_mechanical_cleanup_as_llm_case() -> None:
    entries = _product_positioning_entries()
    source_excerpts = tuple(
        cleanup_helpers._source_excerpts_from_preprocessing_entry(entry)
        for entry in entries
    )

    cleanup = cleanup_helpers._mechanically_cleanup_compiled_entries(
        entries=entries,
        source_excerpts_by_entry=source_excerpts,
    )

    assert len(cleanup.entries) == 2
    assert cleanup.metrics["deterministic_candidate_collapse_count"] == 1

    cases = ars._answer_resolution_cases_from_entries(cleanup.entries)

    assert len(cases) == 1
    assert len(cases[0].candidates) == 2


def test_retighten_uses_same_intent_summary_candidate_generation() -> None:
    entries = _product_positioning_entries()
    source_excerpts = tuple(
        cleanup_helpers._source_excerpts_from_preprocessing_entry(entry)
        for entry in entries
    )
    cleanup = cleanup_helpers._mechanically_cleanup_compiled_entries(
        entries=entries,
        source_excerpts_by_entry=source_excerpts,
    )

    retighten = retighten_helpers._deterministic_retighten_existing_document_plan(
        cleanup.entries
    )

    assert len(retighten.plan.entries) == 2

    cases = ars._answer_resolution_cases_from_entries(retighten.plan.entries)

    assert len(cases) == 1
    assert len(cases[0].candidates) == 2
