from __future__ import annotations

from src.application.services.knowledge_answer_resolution_service import (
    merge_answer_text,
)
from src.application.services.knowledge_compiled_entry_cleanup import (
    cleanup_compiled_entries_mechanically,
)
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingEntry,
)


def _entry(
    *,
    title: str,
    question: str,
    answer: str,
    questions: tuple[str, ...] = (),
    synonyms: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
) -> KnowledgePreprocessingEntry:
    return KnowledgePreprocessingEntry(
        title=title,
        canonical_question=question,
        questions=questions or (question,),
        synonyms=synonyms,
        tags=tags,
        answer=answer,
        source_excerpt=answer,
    )


def test_merge_answer_text_keeps_superset_answer_units() -> None:
    merged = merge_answer_text(
        "Условия возврата зависят от ситуации.",
        ("Условия возврата зависят от ситуации. Лучше передать вопрос менеджеру."),
    )

    assert merged == (
        "Условия возврата зависят от ситуации. Лучше передать вопрос менеджеру."
    )


def test_mechanical_cleanup_unions_overlapping_answer_units() -> None:
    left = _entry(
        title="Возврат средств",
        question="Как работает возврат средств?",
        answer=("Условия возврата зависят от ситуации. Решение принимает менеджер."),
        questions=("Как работает возврат средств?", "Можно вернуть деньги?"),
        synonyms=("возврат",),
        tags=("оплата",),
    )
    right = _entry(
        title="Возврат оплаты",
        question="Как работает возврат средств?",
        answer=("Условия возврата зависят от ситуации. Нужно уточнить этап работы."),
        questions=("Как работает возврат средств?", "Можно вернуть оплату?"),
        synonyms=("вернуть оплату",),
        tags=("деньги",),
    )

    result = cleanup_compiled_entries_mechanically(
        entries=(left, right),
        source_excerpts_by_entry=((left.source_excerpt,), (right.source_excerpt,)),
    )

    assert len(result.entries) == 1
    merged = result.entries[0]
    assert "Условия возврата зависят от ситуации." in merged.answer
    assert "Решение принимает менеджер." in merged.answer
    assert "Нужно уточнить этап работы." in merged.answer
    assert "Можно вернуть деньги?" in merged.questions
    assert "Можно вернуть оплату?" in merged.questions
    assert "возврат" in merged.synonyms
    assert "вернуть оплату" in merged.synonyms
    assert "оплата" in merged.tags
    assert "деньги" in merged.tags
    assert result.metrics["deterministic_candidate_collapse_count"] == 1


def test_mechanical_cleanup_unions_complementary_same_intent_answers() -> None:
    left = _entry(
        title="Стоимость",
        question="Сколько стоит продукт?",
        answer="Стоимость зависит от конфигурации.",
        questions=("Сколько стоит продукт?",),
    )
    right = _entry(
        title="Цена",
        question="Сколько стоит продукт?",
        answer="Для точного расчёта лучше передать запрос менеджеру.",
        questions=("Сколько стоит продукт?", "Какая цена?"),
    )

    result = cleanup_compiled_entries_mechanically(
        entries=(left, right),
        source_excerpts_by_entry=((left.source_excerpt,), (right.source_excerpt,)),
    )

    assert len(result.entries) == 1
    merged = result.entries[0]
    assert "Стоимость зависит от конфигурации." in merged.answer
    assert "Для точного расчёта лучше передать запрос менеджеру." in merged.answer
    assert "Какая цена?" in merged.questions
    assert result.metrics["deterministic_candidate_collapse_count"] == 1


def test_mechanical_cleanup_keeps_different_intents_separate() -> None:
    price = _entry(
        title="Стоимость",
        question="Сколько стоит продукт?",
        answer="Стоимость зависит от конфигурации.",
    )
    launch = _entry(
        title="Срок запуска",
        question="Сколько длится запуск?",
        answer="Запуск занимает несколько рабочих дней.",
    )

    result = cleanup_compiled_entries_mechanically(
        entries=(price, launch),
        source_excerpts_by_entry=((price.source_excerpt,), (launch.source_excerpt,)),
    )

    assert len(result.entries) == 2
