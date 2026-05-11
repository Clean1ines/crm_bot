from __future__ import annotations

SEMANTIC_BUILDER_VERSION = "deterministic_v1"

INTERNAL_EVAL_TEST_MARKERS: tuple[str, ...] = (
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
)

NEGATIVE_TEST_MARKERS: tuple[str, ...] = (
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
)

RETRIEVAL_GUIDELINE_MARKERS: tuple[str, ...] = (
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
)

PRICE_TITLE_MARKERS: tuple[str, ...] = (
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
)

PRICE_BODY_MARKERS: tuple[str, ...] = (
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
)

INSTRUCTION_TITLE_MARKERS: tuple[str, ...] = (
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
)

INSTRUCTION_STEP_MARKERS: tuple[str, ...] = (
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
)

FAQ_TITLE_MARKERS: tuple[str, ...] = (
    "faq",
    "frequently asked",
    "questions and answers",
    "q&a",
    "частые вопросы",
    "вопросы и ответы",
    "чаво",
)

FAQ_ANSWER_MARKERS: tuple[str, ...] = (
    "answer:",
    "question:",
    "q:",
    "a:",
    "ответ:",
    "вопрос:",
)

SEMANTIC_TAG_STOP_WORDS: frozenset[str] = frozenset(
    {
        "база",
        "знаний",
        "раздел",
        "продукта",
        "продукт",
        "для",
        "или",
        "как",
        "что",
        "это",
        "the",
        "and",
        "for",
        "with",
        "from",
        "into",
    }
)

SEMANTIC_TAG_TERM_PATTERN = r"[0-9A-Za-zА-Яа-яЁё_-]+"
MARKDOWN_HEADER_PATTERN = r"^#{1,6}\s+\S"
MARKDOWN_HEADER_STRIP_PATTERN = r"^#{1,6}\s+"

BROAD_NOISY_PRICE_SYNONYMS: frozenset[str] = frozenset(
    {
        "че по цене",
        "что по цене",
        "price pls",
        "price please",
        "скока",
        "сколько стоит",
        "how much this",
        "how much",
        "cost",
        "price",
        "pricing",
    }
)
