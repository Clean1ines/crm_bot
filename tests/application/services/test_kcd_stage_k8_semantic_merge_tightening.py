from __future__ import annotations

from src.application.services.knowledge_ingestion_service import (
    KCD_STAGE_K8_SEMANTIC_MERGE_CANDIDATE_ANSWER_MAX_CHARS,
    _apply_semantic_merge_tightening_decisions,
    _cleanup_semantic_merge_embedding_text,
    _cleanup_semantic_merge_embedding_text_with_metrics,
    _reject_noisy_semantic_merge_decisions,
    _semantic_merge_candidate_from_entry,
    _semantic_merge_suspect_groups_from_entries,
)
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingEntry,
    KnowledgeSemanticMergeDecision,
)


def _entry(
    title: str,
    *,
    answer: str = "Ответ.",
    source_excerpt: str = "Источник.",
    questions: tuple[str, ...] = (),
    synonyms: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    embedding_text: str = "",
) -> KnowledgePreprocessingEntry:
    return KnowledgePreprocessingEntry(
        title=title,
        answer=answer,
        source_excerpt=source_excerpt,
        questions=questions,
        synonyms=synonyms,
        tags=tags,
        embedding_text=embedding_text or f"{title}. {answer}",
    )


def test_stage_k8_builds_generic_suspect_groups_without_domain_labels() -> None:
    entries = (
        _entry(
            "Что нужно для запуска",
            answer="Для запуска нужен токен и база знаний.",
            embedding_text="что нужно для запуска старт подключение токен база знаний",
        ),
        _entry(
            "Что нужно для старта",
            answer="Для старта нужен токен и база знаний.",
            embedding_text="что нужно для старта запуск подключение токен база знаний",
        ),
        _entry(
            "Скорость ответа",
            answer="Ассистент отвечает быстро.",
            embedding_text="скорость ответа время реакции ассистента",
        ),
    )

    groups = _semantic_merge_suspect_groups_from_entries(entries)

    assert len(groups) == 1
    assert groups[0].group_id.startswith("semantic-merge-")
    assert [candidate.candidate_id for candidate in groups[0].candidates] == [
        "entry-0",
        "entry-1",
    ]


def test_stage_k8_applies_llm_merge_decision_to_entries_and_source_excerpts() -> None:
    entries = (
        _entry(
            "Что нужно для запуска",
            answer="Для запуска нужен токен.",
            source_excerpt="Нужен токен.",
            questions=("Что требуется для запуска?",),
            synonyms=("запуск",),
            tags=("start",),
            embedding_text="что нужно для запуска токен",
        ),
        _entry(
            "Что нужно для старта",
            answer="Для старта нужна база знаний.",
            source_excerpt="Нужна база знаний.",
            questions=("Что требуется для старта?",),
            synonyms=("старт",),
            tags=("start",),
            embedding_text="что нужно для старта база знаний",
        ),
    )
    decision = KnowledgeSemanticMergeDecision(
        group_id="semantic-merge-test",
        action="merge",
        candidate_ids=("entry-0", "entry-1"),
        survivor_title="Что нужно для запуска",
        merged_embedding_text=(
            "Что нужно для запуска или старта: токен, база знаний, подключение."
        ),
    )

    tightened, source_excerpts = _apply_semantic_merge_tightening_decisions(
        entries=entries,
        decisions=(decision,),
        source_excerpts_by_entry=(("Нужен токен.",), ("Нужна база знаний.",)),
    )

    assert len(tightened) == 1
    assert len(source_excerpts) == 1
    assert tightened[0].title == "Что нужно для запуска"
    assert source_excerpts[0] == ("Нужен токен.", "Нужна база знаний.")
    assert "Что требуется для запуска?" in tightened[0].questions
    assert "Что требуется для старта?" in tightened[0].questions
    assert "токен" in tightened[0].embedding_text
    assert "база знаний" in tightened[0].embedding_text


def test_stage_k8_keeps_unrelated_entries_out_of_suspect_groups() -> None:
    entries = (
        _entry(
            "Стоимость",
            answer="Стоимость зависит от проекта.",
            embedding_text="стоимость цена тариф бюджет",
        ),
        _entry(
            "Скорость ответа",
            answer="Ассистент отвечает быстро.",
            embedding_text="скорость ответа время реакции",
        ),
    )

    assert _semantic_merge_suspect_groups_from_entries(entries) == ()


def test_stage_k8_semantic_merge_llm_candidate_payload_is_question_aware_and_bounded() -> (
    None
):
    answer = "Полный пользовательский ответ нужен для сравнения смысла. " * 80
    entry = KnowledgePreprocessingEntry(
        title="Возврат книги",
        answer=answer,
        source_excerpt="Источник про возврат книги.",
        questions=("Как вернуть книгу?", "Как оформить возврат книги?"),
        synonyms=("вернуть книгу", "оформить возврат"),
        tags=("возврат", "книга"),
        embedding_text="Возврат книги. Как вернуть книгу. " * 80,
    )

    candidate = _semantic_merge_candidate_from_entry(index=3, entry=entry)

    assert candidate.candidate_id == "entry-3"
    assert candidate.title == "Возврат книги"
    assert candidate.answer
    assert (
        len(candidate.answer) <= KCD_STAGE_K8_SEMANTIC_MERGE_CANDIDATE_ANSWER_MAX_CHARS
    )
    assert candidate.answer.startswith("Полный пользовательский ответ нужен")
    assert candidate.questions == ("Как вернуть книгу?", "Как оформить возврат книги?")
    assert candidate.synonyms == ("вернуть книгу", "оформить возврат")
    assert candidate.tags == ("возврат", "книга")
    assert candidate.embedding_text
    assert candidate.source_ref_count == 1


def test_stage_k8_cleanup_removes_repeated_llm_merge_sentences() -> None:
    text = (
        "AI-ассистент отвечает на вопросы клиентов и сохраняет историю диалогов. "
        "AI-ассистент отвечает на вопросы клиентов и сохраняет историю диалогов. "
        "Историю диалогов можно смотреть в панели проекта. "
        "Историю диалогов можно смотреть в панели проекта."
    )

    cleaned = _cleanup_semantic_merge_embedding_text(text)

    assert cleaned.count("AI-ассистент отвечает") == 1
    assert cleaned.count("Историю диалогов можно смотреть") == 1


def test_stage_k8_cleanup_reports_removed_unit_count() -> None:
    result = _cleanup_semantic_merge_embedding_text_with_metrics(
        "Бот отвечает ночью. Бот отвечает ночью. История диалогов доступна."
    )

    assert result.original_unit_count == 3
    assert result.kept_unit_count == 2
    assert result.removed_unit_count == 1
    assert result.text.count("Бот отвечает ночью") == 1


def test_stage_k8_rejects_noisy_merge_decision_as_keep_separate() -> None:
    decisions = (
        KnowledgeSemanticMergeDecision(
            group_id="semantic-merge-noisy",
            action="merge",
            candidate_ids=("entry-0", "entry-1"),
            survivor_title="История диалогов",
            merged_embedding_text=(
                "История диалогов доступна в панели. "
                "История диалогов доступна в панели. "
                "История диалогов доступна в панели. "
                "История диалогов доступна в панели. "
                "Менеджер может смотреть карточку клиента."
            ),
        ),
    )

    filtered = _reject_noisy_semantic_merge_decisions(decisions)

    assert filtered[0].action == "keep_separate"
    assert filtered[0].candidate_ids == ("entry-0", "entry-1")
    assert filtered[0].merged_embedding_text == ""


# Question-aware pairwise semantic retightening tests


def test_semantic_merge_candidates_keep_answer_and_enrichment_payload() -> None:
    entry = KnowledgePreprocessingEntry(
        title="Возврат книги",
        answer="Возврат книги оформляется через заявку.",
        source_excerpt="Источник про возврат книги.",
        questions=("Как вернуть книгу?",),
        synonyms=("возврат книги",),
        tags=("возврат",),
        embedding_text="Возврат книги. Как вернуть книгу.",
    )

    candidate = _semantic_merge_candidate_from_entry(index=0, entry=entry)

    assert candidate.answer == "Возврат книги оформляется через заявку."
    assert candidate.questions == ("Как вернуть книгу?",)
    assert candidate.synonyms == ("возврат книги",)
    assert candidate.tags == ("возврат",)


def test_semantic_merge_suspect_groups_are_pairwise_and_question_aware() -> None:
    from src.application.services.knowledge_ingestion_service import (
        _semantic_merge_suspect_groups_from_entries,
    )
    from src.domain.project_plane.knowledge_preprocessing import (
        KnowledgePreprocessingEntry,
    )

    first = KnowledgePreprocessingEntry(
        title="Возврат книги",
        answer="Возврат книги оформляется через личный кабинет.",
        source_excerpt="Источник 1.",
        questions=("Как оформить возврат книги?",),
        synonyms=("вернуть книгу",),
        tags=("возврат",),
        embedding_text="Как оформить возврат книги. Вернуть книгу.",
    )
    second = KnowledgePreprocessingEntry(
        title="Как вернуть книгу",
        answer="Книгу можно вернуть через заявку в личном кабинете.",
        source_excerpt="Источник 2.",
        questions=("Можно ли вернуть книгу?",),
        synonyms=("оформить возврат книги",),
        tags=("возврат",),
        embedding_text="Можно ли вернуть книгу. Оформить возврат книги.",
    )
    unrelated = KnowledgePreprocessingEntry(
        title="Продление абонемента",
        answer="Абонемент продлевается отдельной заявкой.",
        source_excerpt="Источник 3.",
        questions=("Как продлить абонемент?",),
        synonyms=("продление абонемента",),
        tags=("абонемент",),
        embedding_text="Как продлить абонемент.",
    )

    groups = _semantic_merge_suspect_groups_from_entries((first, second, unrelated))

    assert groups
    assert all(len(group.candidates) == 2 for group in groups)
    candidate_id_sets = {
        frozenset(candidate.candidate_id for candidate in group.candidates)
        for group in groups
    }
    assert frozenset({"entry-0", "entry-1"}) in candidate_id_sets
    assert frozenset({"entry-0", "entry-2"}) not in candidate_id_sets
    assert frozenset({"entry-1", "entry-2"}) not in candidate_id_sets


def test_merge_answer_text_removes_repeated_sentence_units() -> None:
    from src.application.services.knowledge_ingestion_service import _merge_answer_text

    merged = _merge_answer_text(
        "Документ можно получить ночью. Нужно включить круглосуточный доступ.",
        "Документ можно получить ночью. Заявка сохраняется в истории.",
    )

    assert merged.count("Документ можно получить ночью") == 1
    assert "Нужно включить круглосуточный доступ" in merged
    assert "Заявка сохраняется в истории" in merged
