from __future__ import annotations

import json
from src.application.services.knowledge_ingestion_service import (
    _question_intent_card_from_entry,
    _select_question_intent_cards_for_batch,
)
from src.domain.project_plane.knowledge_preprocessing import KnowledgePreprocessingEntry
from src.infrastructure.llm.knowledge_preprocessor import GroqKnowledgePreprocessor


def _entry(
    title: str,
    *,
    answer: str,
    questions: tuple[str, ...],
    tags: tuple[str, ...] = (),
) -> KnowledgePreprocessingEntry:
    return KnowledgePreprocessingEntry(
        title=title,
        answer=answer,
        source_excerpt=answer,
        questions=questions,
        synonyms=(),
        tags=tags,
        embedding_text=f"{title} {answer} {' '.join(questions)}",
    )


def _preprocessor() -> GroqKnowledgePreprocessor:
    preprocessor = GroqKnowledgePreprocessor.__new__(GroqKnowledgePreprocessor)
    preprocessor._max_chunks = 1
    preprocessor._max_chunk_chars = 900
    return preprocessor


def test_question_intent_selector_prefers_same_information_need_over_shared_topic_words() -> (
    None
):
    price = _entry(
        "Стоимость",
        answer="Подключение стоит 100 рублей в месяц.",
        questions=("Сколько стоит подключение?", "Есть ли абонентская плата?"),
        tags=("цена", "подключение"),
    )
    onboarding = _entry(
        "Подключение",
        answer="Для подключения нужно оставить заявку менеджеру.",
        questions=("Как подключиться?", "Как оставить заявку на подключение?"),
        tags=("подключение", "заявка"),
    )
    handoff = _entry(
        "Передача менеджеру",
        answer="Сложные вопросы ассистент передает менеджеру.",
        questions=("Можно поговорить с человеком?", "Позовите менеджера"),
        tags=("менеджер",),
    )
    cards = tuple(
        _question_intent_card_from_entry(entry, entry_id=f"entry-{index}")
        for index, entry in enumerate((price, onboarding, handoff))
    )
    incoming = _entry(
        "Цена",
        answer="Абонентская плата составляет 100 рублей.",
        questions=("Какая цена?", "Сколько стоит?"),
        tags=("цена",),
    )

    selected = _select_question_intent_cards_for_batch(
        candidates=(incoming,),
        known_cards=cards,
        limit=2,
    )

    assert selected[0].title == "Стоимость"
    assert all(card.title != "Передача менеджеру" for card in selected)


def test_question_intent_selector_returns_highest_score_first_without_title_or_tags_identity() -> (
    None
):
    price = _entry(
        "Display title unrelated to price",
        answer="Базовый тариф стоит 100 рублей в месяц.",
        questions=("Сколько стоит сервис?", "Какая цена тарифа?"),
        tags=("shared",),
    )
    support = _entry(
        "Стоимость",
        answer="Менеджер отвечает на сложные вопросы в рабочее время.",
        questions=("Как связаться с менеджером?", "Когда отвечает поддержка?"),
        tags=("shared", "цена"),
    )
    onboarding = _entry(
        "Тарифы",
        answer="Для подключения нужно оставить заявку.",
        questions=("Как подключиться?", "Как оставить заявку?"),
        tags=("цена",),
    )
    cards = tuple(
        _question_intent_card_from_entry(entry, entry_id=f"entry-{index}")
        for index, entry in enumerate((support, onboarding, price))
    )
    incoming = _entry(
        "Поддержка",
        answer="Премиум тариф стоит 500 рублей в месяц.",
        questions=("Сколько стоит премиум тариф?", "Какая цена тарифа?"),
        tags=("shared", "support"),
    )

    selected = _select_question_intent_cards_for_batch(
        candidates=(incoming,),
        known_cards=cards,
        limit=3,
    )

    assert selected[0].entry_id == "entry-2"
    assert selected[0].primary_question == "Сколько стоит сервис?"
    assert selected[0].question_samples == (
        "Сколько стоит сервис?",
        "Какая цена тарифа?",
    )
    assert selected[0].answer_digest == "Базовый тариф стоит 100 рублей в месяц."


def test_extractor_prompt_omits_known_intents_from_source_payload() -> None:
    existing = _entry(
        "Возврат средств",
        answer="Возврат оформляется через менеджера после проверки заказа.",
        questions=("Можно вернуть деньги?", "Есть возврат?"),
        tags=("возврат",),
    )
    card = _question_intent_card_from_entry(existing, entry_id="compiled-0")

    prompt = _preprocessor()._build_prompt(
        mode="faq",
        chunks=[{"content": "Refund policy: manager checks the order."}],
        file_name="faq.txt",
        previous_question_intents=(card,),
    )

    payload = json.loads(
        prompt.rsplit("ОБРАБОТАЙ SOURCE JSON НИЖЕ. ВЕРНИ ТОЛЬКО JSON:", 1)[1]
    )

    assert "known_question_intents" not in prompt
    assert "previous_answer_titles" not in payload
    assert "previous_entry_titles" not in payload
    assert payload == {
        "file_name": "faq.txt",
        "mode": "faq",
        "chunks": [{"index": 0, "content": "Refund policy: manager checks the order."}],
    }


def test_faq_prompt_requires_split_replacement_answer_and_compact_embedding_text() -> (
    None
):
    prompt = _preprocessor()._build_prompt(
        mode="faq",
        chunks=[{"content": "Цена: 100. Подключение: заявка менеджеру."}],
        file_name="faq.txt",
    )

    assert "Один fragment отвечает на один конкретный клиентский вопрос" in prompt
    assert "Один chunk может дать несколько fragments" in prompt
    assert "Не объединяй результат с предыдущими ответами" in prompt
    assert "Не возвращай match, kind, known_intent_id" in prompt
    assert "answer_fragment" in prompt


def test_semantic_merge_prompt_requires_replacement_not_append_and_keeps_related_intents() -> (
    None
):
    prompt = _preprocessor()._build_semantic_merge_tightening_prompt(
        mode="faq",
        file_name="faq.txt",
        groups=(),
    )

    assert "same answer intent / stable user information need" in prompt
    assert "Do NOT append old answer + new answer" in prompt
    assert "return A+B once, not A+A+B" in prompt
    assert "keep separate price vs onboarding" in prompt
    assert "embedding_text as the primary identity signal" in prompt
