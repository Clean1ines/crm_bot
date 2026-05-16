from __future__ import annotations

import asyncio
import json

import pytest

from src.application.services.knowledge_ingestion_service import (
    _apply_semantic_merge_tightening_decisions,
    _mechanically_cleanup_compiled_entries,
    _answer_resolution_decisions_with_case_candidate_ids,
    _semantic_merge_suspect_groups_from_entries,
    _tighten_compiled_entries_with_semantic_merge,
)
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingEntry,
    KnowledgePreprocessingValidationError,
    KnowledgeAnswerResolutionDecision,
    KnowledgeAnswerResolverExecutionResult,
    parse_answer_resolution_payload,
)
from src.infrastructure.llm.knowledge_preprocessor import GroqKnowledgePreprocessor

FORBIDDEN_RESOLVER_FIELDS = {
    "questions",
    "synonyms",
    "tags",
    "embedding_text",
    "metadata",
    "source_refs",
    "source_chunk_indexes",
    "source_ref_count",
    "title",
    "canonical" + "_card",
    "entries",
    "cards",
}


def _entry(
    *,
    title: str,
    question: str,
    answer: str,
    source_excerpt: str | None = None,
    questions: tuple[str, ...] = (),
    synonyms: tuple[str, ...] = (),
    tags: tuple[str, ...] = (),
    embedding_text: str = "",
    source_chunk_indexes: tuple[int, ...] = (),
) -> KnowledgePreprocessingEntry:
    return KnowledgePreprocessingEntry(
        title=title,
        canonical_question=question,
        questions=questions or (question,),
        synonyms=synonyms,
        tags=tags,
        answer=answer,
        source_excerpt=source_excerpt or answer,
        embedding_text=embedding_text,
        source_chunk_indexes=source_chunk_indexes,
    )


def _prompt_payload(prompt: str) -> dict[str, object]:
    marker = "NOW PROCESS THIS JSON. Return ONLY the JSON result:\n"
    return json.loads(prompt.split(marker, 1)[1])


def test_answer_only_group_payload_excludes_entry_enrichment_and_retrieval_fields() -> (
    None
):
    left = _entry(
        title="Возврат",
        question="Как оформить возврат?",
        answer="Возврат зависит от этапа работы.",
        questions=("Как оформить возврат?", "Можно вернуть оплату?"),
        synonyms=("возврат",),
        tags=("billing",),
        embedding_text="Как оформить возврат Возврат зависит от этапа работы.",
    )
    right = _entry(
        title="Возврат средств",
        question="Как оформить возврат?",
        answer="Решение по возврату принимает менеджер.",
        questions=("Как оформить возврат?", "Вернёте деньги?"),
        synonyms=("вернуть деньги",),
        tags=("refund",),
        embedding_text="Вернёте деньги Решение по возврату принимает менеджер.",
    )

    groups = _semantic_merge_suspect_groups_from_entries((left, right))

    assert len(groups) == 1
    payload = groups[0].to_payload()
    assert set(payload) == {"case_id", "question_intent", "answers"}
    answer_payload = payload["answers"]
    assert isinstance(answer_payload, list)
    assert answer_payload
    assert set(answer_payload[0]) == {"id", "answer", "source_excerpt"}
    serialized = json.dumps(payload, ensure_ascii=False)
    for forbidden in FORBIDDEN_RESOLVER_FIELDS:
        assert f'"{forbidden}"' not in serialized


def test_llm_prompt_payload_contains_only_answer_resolution_cases() -> None:
    entries = (
        _entry(
            title="Возврат",
            question="Как оформить возврат?",
            answer="Возврат зависит от этапа работы.",
            questions=("Как оформить возврат?",),
            synonyms=("возврат",),
            tags=("billing",),
            embedding_text="retrieval text must not leak",
        ),
        _entry(
            title="Возврат средств",
            question="Как оформить возврат?",
            answer="Решение принимает менеджер.",
            questions=("Как оформить возврат?",),
            synonyms=("вернуть деньги",),
            tags=("refund",),
            embedding_text="another retrieval text must not leak",
        ),
    )
    groups = _semantic_merge_suspect_groups_from_entries(entries)
    preprocessor = GroqKnowledgePreprocessor(client=object(), model="test-model")

    prompt = preprocessor._build_answer_resolution_prompt(
        mode="plain",
        file_name="faq.md",
        cases=groups,
        existing_project_titles=("Existing title",),
    )
    payload = _prompt_payload(prompt)

    assert set(payload) == {"file_name", "mode", "existing_project_titles", "cases"}
    serialized = json.dumps(payload["cases"], ensure_ascii=False)
    for forbidden in FORBIDDEN_RESOLVER_FIELDS:
        assert f'"{forbidden}"' not in serialized


def test_answer_resolution_output_cannot_override_enrichment_or_evidence() -> None:
    entries = (
        _entry(
            title="Возврат",
            question="Как оформить возврат?",
            answer="Возврат зависит от ситуации.",
            source_excerpt="Источник A.",
            questions=("Как оформить возврат?", "Можно вернуть деньги?"),
            synonyms=("возврат",),
            tags=("billing",),
            source_chunk_indexes=(0,),
        ),
        _entry(
            title="Возврат средств",
            question="Как оформить возврат?",
            answer="Решение принимает менеджер.",
            source_excerpt="Источник B.",
            questions=("Как оформить возврат?", "Вернёте оплату?"),
            synonyms=("вернуть оплату",),
            tags=("refund",),
            source_chunk_indexes=(1,),
        ),
    )
    decision = KnowledgeAnswerResolutionDecision(
        case_id="group-1",
        action="merge",
        candidate_ids=("entry-0", "entry-1"),
        canonical_answer="Возврат зависит от ситуации; решение принимает менеджер.",
    )

    tightened, source_excerpts = _apply_semantic_merge_tightening_decisions(
        entries=entries,
        decisions=(decision,),
        source_excerpts_by_entry=(("Источник A.",), ("Источник B.",)),
    )

    assert len(tightened) == 1
    entry = tightened[0]
    assert entry.answer == "Возврат зависит от ситуации; решение принимает менеджер."
    assert entry.questions == (
        "Как оформить возврат?",
        "Можно вернуть деньги?",
        "Вернёте оплату?",
    )
    assert entry.synonyms == ("возврат", "вернуть оплату")
    assert entry.tags == ("billing", "refund")
    assert entry.source_chunk_indexes == (0, 1)
    assert source_excerpts == (("Источник A.", "Источник B."),)
    assert entry.embedding_text == (
        "Возврат Как оформить возврат? Как оформить возврат? "
        "Можно вернуть деньги? Вернёте оплату? возврат вернуть оплату billing refund "
        "Возврат зависит от ситуации; решение принимает менеджер."
    )
    assert "LLM" not in entry.embedding_text


def test_answer_resolution_parser_rejects_forbidden_output_fields() -> None:
    with pytest.raises(KnowledgePreprocessingValidationError, match="forbidden fields"):
        parse_answer_resolution_payload(
            {
                "decisions": [
                    {
                        "case_id": "case-1",
                        "action": "merge",
                        "canonical_answer": "Итоговый ответ.",
                        "reason": "same answer",
                        "confidence": 0.9,
                        "questions": ["LLM question"],
                        "synonyms": ["LLM synonym"],
                        "tags": ["LLM tag"],
                        "source_refs": ["ref"],
                        "source_chunk_indexes": [0],
                        "source_excerpt": "LLM evidence overwrite",
                        "embedding_text": "LLM embedding",
                        "metadata": {"unsafe": True},
                        "cards": [{"answer": "ignored"}],
                        "entries": [{"answer": "ignored"}],
                    }
                ]
            },
            mode="plain",
            model="test-model",
        )


def test_answer_resolution_parser_requires_case_id_and_rejects_group_id_fallback() -> (
    None
):
    with pytest.raises(KnowledgePreprocessingValidationError, match="forbidden fields"):
        parse_answer_resolution_payload(
            {
                "decisions": [
                    {
                        "group_id": "legacy-group",
                        "action": "merge",
                        "canonical_answer": "Итоговый ответ.",
                    }
                ]
            },
            mode="plain",
            model="test-model",
        )

    with pytest.raises(KnowledgePreprocessingValidationError, match="case_id"):
        parse_answer_resolution_payload(
            {
                "decisions": [
                    {
                        "action": "merge",
                        "canonical_answer": "Итоговый ответ.",
                    }
                ]
            },
            mode="plain",
            model="test-model",
        )


def test_answer_resolution_parser_rejects_candidate_ids_from_resolver_output() -> None:
    with pytest.raises(KnowledgePreprocessingValidationError, match="candidate_ids"):
        parse_answer_resolution_payload(
            {
                "decisions": [
                    {
                        "case_id": "case-1",
                        "action": "merge",
                        "candidate_ids": ["entry-0", "entry-1"],
                        "canonical_answer": "Итоговый ответ.",
                    }
                ]
            },
            mode="plain",
            model="test-model",
        )


def test_answer_only_case_id_is_mapped_back_to_original_candidate_ids() -> None:
    group = _semantic_merge_suspect_groups_from_entries(
        (
            _entry(
                title="Возврат",
                question="Как оформить возврат?",
                answer="Возврат зависит от ситуации.",
            ),
            _entry(
                title="Возврат средств",
                question="Как оформить возврат?",
                answer="Решение принимает менеджер.",
            ),
        )
    )[0]
    decision = KnowledgeAnswerResolutionDecision(
        case_id=group.case_id,
        action="merge",
        candidate_ids=(),
        canonical_answer="Итоговый ответ.",
    )

    mapped = _answer_resolution_decisions_with_case_candidate_ids(
        group=group,
        decisions=(decision,),
    )

    assert mapped[0].candidate_ids == tuple(candidate.id for candidate in group.answers)


class _FailingPreprocessor:
    async def resolve_answer_cases(
        self, **_: object
    ) -> KnowledgeAnswerResolverExecutionResult:
        raise AssertionError(
            "LLM resolver must not be called after deterministic collapse"
        )


def test_deterministic_cleanup_collapses_exact_answers_before_llm_resolver() -> None:
    left = _entry(
        title="Возврат",
        question="Как оформить возврат?",
        answer="Возврат зависит от ситуации.",
    )
    right = _entry(
        title="Возврат средств",
        question="Как оформить возврат?",
        answer="Возврат зависит от ситуации.",
    )
    cleanup = _mechanically_cleanup_compiled_entries(
        entries=(left, right),
        source_excerpts_by_entry=((left.source_excerpt,), (right.source_excerpt,)),
    )

    tightened, _, metrics = asyncio.run(
        _tighten_compiled_entries_with_semantic_merge(
            preprocessor=_FailingPreprocessor(),
            mode="plain",
            file_name="faq.md",
            entries=cleanup.entries,
            source_excerpts_by_entry=cleanup.source_excerpts_by_entry,
            existing_project_titles=(),
        )
    )

    assert len(cleanup.entries) == 1
    assert tightened == cleanup.entries
    assert metrics["llm_call_count"] == 0
