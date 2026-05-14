from __future__ import annotations

from src.application.services.knowledge_ingestion_service import (
    KCD_STAGE_K8_SEMANTIC_MERGE_CANDIDATE_EMBEDDING_TEXT_MAX_CHARS,
    _apply_semantic_merge_tightening_decisions,
    _cleanup_semantic_merge_embedding_text,
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


def test_stage_k8_semantic_merge_llm_candidate_payload_is_compact() -> None:
    entry = KnowledgePreprocessingEntry(
        title="Условия возврата",
        answer="Полный пользовательский ответ не должен уходить во второй LLM-вызов.",
        source_excerpt="Источник остаётся в детерминированном merge, а не в prompt payload.",
        questions=("Как оформить возврат?",),
        synonyms=("возврат", "refund"),
        tags=("policy",),
        embedding_text="Условия возврата " + ("очень длинный embedding text " * 200),
    )

    candidate = _semantic_merge_candidate_from_entry(index=3, entry=entry)

    assert candidate.candidate_id == "entry-3"
    assert candidate.title == "Условия возврата"
    assert candidate.answer == ""
    assert candidate.questions == ()
    assert candidate.synonyms == ()
    assert candidate.tags == ()
    assert candidate.source_ref_count == 1
    assert len(candidate.embedding_text) <= (
        KCD_STAGE_K8_SEMANTIC_MERGE_CANDIDATE_EMBEDDING_TEXT_MAX_CHARS
    )
    assert "Полный пользовательский ответ" not in candidate.embedding_text
    assert "Источник остаётся" not in candidate.embedding_text


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
