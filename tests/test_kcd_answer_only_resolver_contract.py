from __future__ import annotations

import asyncio
import json

from src.application.services.knowledge_ingestion_service import (
    _apply_semantic_merge_tightening_decisions,
    _mechanically_cleanup_compiled_entries,
    _semantic_merge_decisions_with_group_candidate_ids,
    _semantic_merge_suspect_groups_from_entries,
    _tighten_compiled_entries_with_semantic_merge,
)
from src.domain.project_plane.knowledge_preprocessing import (
    KnowledgePreprocessingEntry,
    KnowledgeSemanticMergeCanonicalCard,
    KnowledgeSemanticMergeDecision,
    KnowledgeSemanticMergeExecutionResult,
    parse_semantic_merge_tightening_payload,
)
from src.infrastructure.llm.knowledge_preprocessor import GroqKnowledgePreprocessor


FORBIDDEN_RESOLVER_FIELDS = {
    "questions",
    "synonyms",
    "tags",
    "embedding_text",
    "metadata",
    "source_refs",
    "source_ref_count",
    "canonical_card",
    "title",
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

    prompt = preprocessor._build_semantic_merge_tightening_prompt(
        mode="plain",
        file_name="faq.md",
        groups=groups,
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
    decision = KnowledgeSemanticMergeDecision(
        group_id="group-1",
        action="merge",
        candidate_ids=("entry-0", "entry-1"),
        merged_embedding_text="Возврат зависит от ситуации; решение принимает менеджер.",
        canonical_card=KnowledgeSemanticMergeCanonicalCard(
            title="LLM title",
            canonical_question="LLM question",
            answer="LLM card answer must be ignored.",
            questions=("LLM question",),
            synonyms=("llm synonym",),
            tags=("llm-tag",),
            source_chunk_indexes=(999,),
        ),
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
        "Можно вернуть деньги? Вернёте оплату? Возврат зависит от ситуации; "
        "решение принимает менеджер."
    )
    assert "LLM" not in entry.embedding_text


def test_answer_resolution_parser_ignores_forbidden_legacy_fields() -> None:
    result = parse_semantic_merge_tightening_payload(
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
                    "embedding_text": "LLM embedding",
                    "metadata": {"unsafe": True},
                    "canonical_card": {
                        "title": "LLM title",
                        "answer": "LLM card answer",
                        "publishable": False,
                    },
                }
            ]
        },
        mode="plain",
        model="test-model",
    )

    decision = result.decisions[0]
    assert decision.group_id == "case-1"
    assert decision.is_merge
    assert decision.merged_embedding_text == "Итоговый ответ."
    assert decision.canonical_card is None


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
    decision = KnowledgeSemanticMergeDecision(
        group_id=group.group_id,
        action="merge",
        candidate_ids=(),
        merged_embedding_text="Итоговый ответ.",
    )

    mapped = _semantic_merge_decisions_with_group_candidate_ids(
        group=group,
        decisions=(decision,),
    )

    assert mapped[0].candidate_ids == tuple(
        candidate.candidate_id for candidate in group.candidates
    )


class _FailingPreprocessor:
    async def tighten_semantic_merges(
        self, **_: object
    ) -> KnowledgeSemanticMergeExecutionResult:
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
