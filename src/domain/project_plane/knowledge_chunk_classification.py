from __future__ import annotations

from dataclasses import dataclass

from src.domain.project_plane.knowledge_chunks import KnowledgeChunkRole


@dataclass(frozen=True, slots=True)
class KnowledgeChunkClassificationInput:
    title: str = ""
    header: str = ""
    body: str = ""
    parent_title: str = ""
    questions: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()


def classify_knowledge_chunk_role(
    value: KnowledgeChunkClassificationInput,
) -> KnowledgeChunkRole:
    title_text = _normalize(" ".join((value.title, value.header, value.parent_title)))
    body_text = _normalize(value.body)
    combined = _normalize(
        " ".join(
            (
                value.title,
                value.header,
                value.parent_title,
                value.body[:1600],
                " ".join(value.questions),
                " ".join(value.tags),
            )
        )
    )

    if _looks_like_retrieval_guideline(combined):
        return KnowledgeChunkRole.RETRIEVAL_GUIDELINE

    if _looks_like_negative_test(combined):
        return KnowledgeChunkRole.NEGATIVE_TEST

    if _looks_like_internal_eval_test(combined):
        return KnowledgeChunkRole.INTERNAL_EVAL_TEST

    if _looks_like_price_list(title_text, body_text):
        return KnowledgeChunkRole.PRICE_LIST

    if _looks_like_instruction(title_text, body_text):
        return KnowledgeChunkRole.INSTRUCTION

    if _looks_like_faq(title_text, body_text):
        return KnowledgeChunkRole.FAQ

    return KnowledgeChunkRole.ANSWER_KNOWLEDGE


def _normalize(value: str) -> str:
    return " ".join(value.lower().replace("ё", "е").split())


def _contains_any(value: str, markers: tuple[str, ...]) -> bool:
    return any(marker in value for marker in markers)


def _looks_like_internal_eval_test(value: str) -> bool:
    return _contains_any(
        value,
        (
            "expected answer",
            "expected topic",
            "expected result",
            "expected chunk",
            "test question",
            "test questions",
            "evaluation question",
            "eval question",
            "regression case",
            "regression test",
            "ожидаемый ответ",
            "ожидаемая тема",
            "ожидаемый результат",
            "тестовый вопрос",
            "тестовые вопросы",
            "проверка базы знаний",
            "регрессионный тест",
        ),
    )


def _looks_like_negative_test(value: str) -> bool:
    return _contains_any(
        value,
        (
            "negative test",
            "negative case",
            "must not answer",
            "should not answer",
            "unsupported question",
            "outside knowledge base",
            "do not hallucinate",
            "hallucination trap",
            "негативный тест",
            "негативные тесты",
            "не должен отвечать",
            "не должна отвечать",
            "вне базы знаний",
            "не выдумывать",
            "ловушка галлюцинации",
        ),
    )


def _looks_like_retrieval_guideline(value: str) -> bool:
    return _contains_any(
        value,
        (
            "retrieval guideline",
            "retrieval rule",
            "rag guideline",
            "rag rule",
            "rag search rule",
            "chunking guideline",
            "embedding guideline",
            "reranking guideline",
            "правило rag",
            "правило для rag",
            "правило поиска",
            "правило для поиска",
            "правило чанкинга",
            "правило разбиения",
            "правило эмбеддинга",
            "не смешивать темы",
        ),
    )


def _looks_like_price_list(title_text: str, body_text: str) -> bool:
    price_title = _contains_any(
        title_text,
        (
            "price",
            "pricing",
            "tariff",
            "tariffs",
            "cost",
            "fee",
            "fees",
            "цена",
            "цены",
            "стоимость",
            "тариф",
            "тарифы",
            "прайс",
            "оплата",
        ),
    )
    price_body = _contains_any(
        body_text,
        (
            "$",
            "€",
            "₽",
            "usd",
            "eur",
            "rub",
            "per month",
            "per year",
            "monthly",
            "yearly",
            "в месяц",
            "в год",
            "руб",
            "руб.",
        ),
    )
    return price_title and price_body


def _looks_like_instruction(title_text: str, body_text: str) -> bool:
    instruction_title = _contains_any(
        title_text,
        (
            "instruction",
            "instructions",
            "how to",
            "setup",
            "onboarding",
            "guide",
            "manual",
            "procedure",
            "runbook",
            "инструкция",
            "инструкции",
            "как настроить",
            "как подключить",
            "руководство",
            "регламент",
            "процедура",
            "онбординг",
        ),
    )
    step_body = _contains_any(
        body_text,
        (
            "step 1",
            "step one",
            "first,",
            "then,",
            "finally,",
            "1.",
            "2.",
            "3.",
            "шаг 1",
            "сначала",
            "затем",
            "после этого",
        ),
    )
    return instruction_title and step_body


def _looks_like_faq(title_text: str, body_text: str) -> bool:
    faq_title = _contains_any(
        title_text,
        (
            "faq",
            "frequently asked",
            "questions and answers",
            "q&a",
            "частые вопросы",
            "вопросы и ответы",
            "чаво",
        ),
    )
    answer_marker = _contains_any(
        body_text,
        (
            "answer:",
            "question:",
            "q:",
            "a:",
            "ответ:",
            "вопрос:",
        ),
    )
    return faq_title or answer_marker
