from __future__ import annotations

from src.application.workbench.answer_deduplication import (
    WorkbenchAnswerDeduplicationCandidate,
    WorkbenchAnswerDeduplicationDecision,
    cleanup_answer_text,
    deduplicate_workbench_answer_candidates,
)


def _product_positioning_cards() -> tuple[WorkbenchAnswerDeduplicationCandidate, ...]:
    return (
        WorkbenchAnswerDeduplicationCandidate(
            candidate_id="positioning-summary",
            canonical_question="Что это за продукт?",
            variants=(
                "Как позиционируется продукт?",
                "Что делает платформа?",
            ),
            answer=(
                "Продукт — это платформа управления AI-базами знаний для бизнеса.\n"
                "Она помогает загрузить документы, извлечь знания, проверить качество поиска "
                "и подключить готовые знания к клиентскому ассистенту."
            ),
            evidence_quotes=(
                "Продукт — это платформа управления AI-базами знаний для бизнеса.",
            ),
            source_refs=(
                {
                    "section_key": "positioning",
                    "quote": "Продукт — это платформа управления AI-базами знаний.",
                },
            ),
        ),
        WorkbenchAnswerDeduplicationCandidate(
            candidate_id="product-short",
            canonical_question="Коротко, что это за продукт?",
            variants=(
                "Что входит в продукт?",
                "Что объединяет продукт?",
            ),
            answer=(
                "Продукт объединяет базу знаний, инструменты проверки качества, "
                "AI-ассистента, Telegram-бота и веб-панель для команды."
            ),
            evidence_quotes=(
                "Продукт объединяет базу знаний, инструменты проверки качества, "
                "AI-ассистента, Telegram-бота и веб-панель.",
            ),
            source_refs=(
                {
                    "section_key": "short_product",
                    "quote": "Продукт объединяет базу знаний и веб-панель.",
                },
            ),
        ),
        WorkbenchAnswerDeduplicationCandidate(
            candidate_id="product-definition",
            canonical_question="Что это за продукт?",
            variants=(
                "Для чего нужна платформа?",
                "Что делает система?",
            ),
            answer=(
                "Продукт — это платформа управления AI-базами знаний для бизнеса.\n"
                "Она помогает загрузить документы, извлечь знания, проверить качество поиска "
                "и подключить готовые знания к клиентскому ассистенту.\n"
                "Готовую базу можно использовать в Telegram-ассистенте."
            ),
            evidence_quotes=(
                "Готовую базу можно использовать в клиентском Telegram-ассистенте.",
            ),
            source_refs=(
                {
                    "section_key": "definition",
                    "quote": "Готовую базу можно использовать в Telegram-ассистенте.",
                },
            ),
        ),
    )


def test_same_canonical_question_cards_merge_mechanically() -> None:
    result = deduplicate_workbench_answer_candidates(_product_positioning_cards())

    assert result.retained_count == 2
    assert result.absorbed_count == 1
    assert result.merges[0].decision is (
        WorkbenchAnswerDeduplicationDecision.MERGE_EXACT_OR_CONTAINED
    )
    assert result.merges[0].survivor_candidate_id == "positioning-summary"
    assert result.merges[0].absorbed_candidate_ids == ("product-definition",)

    merged_product_card = result.candidates[0]
    assert merged_product_card.candidate_id == "positioning-summary"
    assert merged_product_card.canonical_question == "Что это за продукт?"
    assert merged_product_card.answer == (
        "Продукт — это платформа управления AI-базами знаний для бизнеса.\n"
        "Она помогает загрузить документы, извлечь знания, проверить качество поиска "
        "и подключить готовые знания к клиентскому ассистенту.\n"
        "Готовую базу можно использовать в Telegram-ассистенте."
    )
    assert merged_product_card.source_refs == (
        {
            "section_key": "positioning",
            "quote": "Продукт — это платформа управления AI-базами знаний.",
        },
        {
            "section_key": "definition",
            "quote": "Готовую базу можно использовать в Telegram-ассистенте.",
        },
    )


def test_different_canonical_questions_remain_separate_even_when_topic_overlaps() -> (
    None
):
    result = deduplicate_workbench_answer_candidates(_product_positioning_cards())

    canonical_questions = tuple(
        candidate.canonical_question for candidate in result.candidates
    )

    assert canonical_questions == (
        "Что это за продукт?",
        "Коротко, что это за продукт?",
    )


def test_repeated_answer_units_are_collapsed_without_old_cleanup_service() -> None:
    assert cleanup_answer_text(
        "Продукт — это платформа управления AI-базами знаний.\n"
        "Продукт — это платформа управления AI-базами знаний.\n"
        "Она подключается к клиентскому ассистенту."
    ) == (
        "Продукт — это платформа управления AI-базами знаний.\n"
        "Она подключается к клиентскому ассистенту."
    )


def test_variants_do_not_split_canonical_question_group() -> None:
    result = deduplicate_workbench_answer_candidates(
        (
            WorkbenchAnswerDeduplicationCandidate(
                candidate_id="a",
                canonical_question="Что это за продукт?",
                variants=("Как позиционируется продукт?",),
                answer="Это платформа управления AI-базами знаний.",
            ),
            WorkbenchAnswerDeduplicationCandidate(
                candidate_id="b",
                canonical_question="Что это за продукт?",
                variants=("Что делает система?",),
                answer=(
                    "Это платформа управления AI-базами знаний.\n"
                    "Она подключается к клиентскому ассистенту."
                ),
            ),
        )
    )

    assert result.retained_count == 1
    assert result.absorbed_count == 1
    assert result.candidates[0].variants == (
        "Что это за продукт?",
        "Как позиционируется продукт?",
        "Что делает система?",
    )


def test_semantic_only_overlap_is_not_merged_mechanically() -> None:
    result = deduplicate_workbench_answer_candidates(
        (
            WorkbenchAnswerDeduplicationCandidate(
                candidate_id="a",
                canonical_question="Что это за продукт?",
                answer="Это платформа управления AI-базами знаний.",
            ),
            WorkbenchAnswerDeduplicationCandidate(
                candidate_id="b",
                canonical_question="Что это за продукт?",
                answer="Система помогает менеджерам отвечать клиентам быстрее.",
            ),
        )
    )

    assert result.retained_count == 2
    assert result.absorbed_count == 0
    assert result.merges == ()
