from __future__ import annotations

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

    assert selected[-1].title == "Стоимость"
    assert all(card.title != "Передача менеджеру" for card in selected)


def test_question_first_prompt_uses_intent_cards_not_titles_as_identity_source() -> (
    None
):
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
        previous_entry_titles=("Возврат средств",),
        previous_question_intents=(card,),
    )

    assert "known_question_intents" in prompt
    assert "previous_answer_titles is fallback naming context only" in prompt
    assert "reuse the exact previous title" in prompt
    assert "Same answer intent means the same stable user information need" in prompt
    assert "Never append old answer text plus new answer text" in prompt
    assert "Можно вернуть деньги?" in prompt


def test_faq_prompt_requires_split_replacement_answer_and_compact_embedding_text() -> (
    None
):
    prompt = _preprocessor()._build_prompt(
        mode="faq",
        chunks=[{"content": "Цена: 100. Подключение: заявка менеджеру."}],
        file_name="faq.txt",
    )

    assert "One entry = one answer intent / one stable user information need" in prompt
    assert "Split a multi-topic source fragment into multiple entries" in prompt
    assert "replacement canonical answer A+B once" in prompt
    assert "never append A + rephrased A + B" in prompt
    assert "not the full source_excerpt" in prompt


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
