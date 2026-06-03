from __future__ import annotations

from src.application.workbench.answer_deduplication import (
    WorkbenchAnswerDeduplicationCandidate,
    WorkbenchAnswerDeduplicationDecision,
    cleanup_answer_text,
    deduplicate_workbench_answer_candidates,
    merge_answer_units_deterministically,
    question_intent_fingerprint,
)


def test_question_intent_fingerprint_uses_question_and_variants() -> None:
    left = question_intent_fingerprint(
        "Как оплатить заказ?",
        "Какие способы оплаты?",
    )
    right = question_intent_fingerprint(
        "Как оплатить заказ?",
        "Какие способы оплаты?",
    )

    assert left
    assert left == right


def test_cleanup_answer_text_removes_exact_duplicate_units() -> None:
    assert (
        cleanup_answer_text(
            "Оплатить можно картой.\nОплатить можно картой.\nТакже доступен перевод."
        )
        == "Оплатить можно картой.\nТакже доступен перевод."
    )


def test_merge_answer_units_deterministically_merges_exact_units() -> None:
    result = merge_answer_units_deterministically(
        "Оплатить можно картой.\nТакже доступен перевод.",
        "Оплатить можно картой.\nТакже доступен перевод.",
    )

    assert result is not None
    assert result.strategy == "exact_same_answer_units"
    assert result.merged_unit_count == 2


def test_merge_answer_units_deterministically_prefers_more_complete_answer() -> None:
    result = merge_answer_units_deterministically(
        "Оплатить можно картой.",
        "Оплатить можно картой.\nТакже доступен перевод.",
    )

    assert result is not None
    assert result.strategy == "right_contains_left_answer_units"
    assert result.answer == "Оплатить можно картой.\nТакже доступен перевод."


def test_deduplicate_workbench_answer_candidates_collapses_same_question_same_answer_units() -> (
    None
):
    result = deduplicate_workbench_answer_candidates(
        (
            WorkbenchAnswerDeduplicationCandidate(
                candidate_id="a",
                canonical_question="Как оплатить заказ?",
                variants=("Какие способы оплаты?",),
                answer="Оплатить можно картой.",
                evidence_quotes=("В документе: оплатить можно картой",),
                source_refs=({"section_id": "s1", "quote": "оплатить можно картой"},),
            ),
            WorkbenchAnswerDeduplicationCandidate(
                candidate_id="b",
                canonical_question="Как оплатить заказ?",
                variants=("Как оплатить заказ?",),
                answer="Оплатить можно картой.\nТакже доступен перевод.",
                evidence_quotes=("В документе: также доступен перевод",),
                source_refs=({"section_id": "s2", "quote": "также доступен перевод"},),
            ),
        )
    )

    assert result.retained_count == 1
    assert result.absorbed_count == 1
    assert (
        result.merges[0].decision
        is WorkbenchAnswerDeduplicationDecision.MERGE_EXACT_OR_CONTAINED
    )
    assert result.merges[0].absorbed_candidate_ids == ("b",)
    assert (
        result.candidates[0].answer == "Оплатить можно картой.\nТакже доступен перевод."
    )
    assert result.candidates[0].evidence_quotes == (
        "В документе: оплатить можно картой",
        "В документе: также доступен перевод",
    )
    assert result.candidates[0].source_refs == (
        {"section_id": "s1", "quote": "оплатить можно картой"},
        {"section_id": "s2", "quote": "также доступен перевод"},
    )


def test_deduplicate_workbench_answer_candidates_keeps_semantic_only_overlap_separate() -> (
    None
):
    result = deduplicate_workbench_answer_candidates(
        (
            WorkbenchAnswerDeduplicationCandidate(
                candidate_id="a",
                canonical_question="Как оплатить заказ?",
                answer="Оплатить можно картой.",
            ),
            WorkbenchAnswerDeduplicationCandidate(
                candidate_id="b",
                canonical_question="Как оплатить заказ?",
                answer="Оплата принимается через личный кабинет.",
            ),
        )
    )

    assert result.retained_count == 2
    assert result.absorbed_count == 0
    assert result.merges == ()


def test_dedup_node_does_not_model_old_answer_candidate_or_cluster() -> None:
    candidate = WorkbenchAnswerDeduplicationCandidate(
        candidate_id="a",
        canonical_question="Что такое продукт?",
        answer="Это CRM-бот.",
    )

    assert not hasattr(candidate, "compiler_run_id")
    assert not hasattr(candidate, "cluster_key")
    assert not hasattr(candidate, "candidate_answer")


def test_deduplicate_workbench_answer_candidates_uses_variants_as_metadata_not_group_key() -> (
    None
):
    result = deduplicate_workbench_answer_candidates(
        (
            WorkbenchAnswerDeduplicationCandidate(
                candidate_id="a",
                canonical_question="Как оплатить заказ?",
                variants=("Какие способы оплаты?",),
                answer="Оплатить можно картой.",
            ),
            WorkbenchAnswerDeduplicationCandidate(
                candidate_id="b",
                canonical_question="Как оплатить заказ?",
                variants=("Можно ли оплатить банковским переводом?",),
                answer="Оплатить можно картой.\nТакже доступен перевод.",
            ),
        )
    )

    assert result.retained_count == 1
    assert result.absorbed_count == 1
    assert result.candidates[0].variants == (
        "Как оплатить заказ?",
        "Какие способы оплаты?",
        "Можно ли оплатить банковским переводом?",
    )


def test_answer_deduplication_delegates_answer_unit_policy_to_domain() -> None:
    import src.application.workbench.answer_deduplication as module

    source = module.__loader__.get_source(module.__name__)
    assert source is not None
    assert "knowledge_workbench.answer_unit_policy" in source
    assert "knowledge_answer_resolution_service" not in source
    assert "knowledge_compiled_entry_cleanup" not in source
