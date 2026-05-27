from __future__ import annotations

from src.domain.project_plane.retrieval_surface_graph import (
    QuestionOwnership,
    SurfaceCandidate,
    SurfaceRelation,
    reconcile_surface_graph,
)


def test_surface_graph_handles_late_parent_merge_and_non_overlapping_question_ownership() -> None:
    candidates = [
        SurfaceCandidate(
            key="surface_1",
            title="1",
            kind="umbrella",
            source_unit_key="unit_1",
            answer_scope="Общий обзор группы 1.",
            question_scope="Только общие вопросы о группе 1.",
            exclusion_scope="Не отвечать на узкие вопросы a+d, b, c*c', g.",
        ),
        SurfaceCandidate(
            key="surface_2",
            title="2",
            kind="umbrella",
            source_unit_key="unit_2",
            answer_scope="Общий обзор группы 2.",
            question_scope="Только общие вопросы о группе 2.",
            exclusion_scope="Не отвечать на узкие вопросы a+d, b, c*c', j.",
        ),
        SurfaceCandidate(
            key="surface_a",
            title="A",
            kind="umbrella",
            source_unit_key="unit_a",
            answer_scope="Мегазонтичный обзор для групп 1 и 2.",
            question_scope="Только самые общие вопросы про A как верхний раздел.",
            exclusion_scope="Не отвечать на вопросы, принадлежащие 1, 2 или их детям.",
        ),
        SurfaceCandidate(
            key="knowledge_a",
            title="a",
            kind="specific",
            source_unit_key="unit_1",
            answer_scope="Узкое знание a.",
            question_scope="Только вопросы про a.",
            exclusion_scope="Не отвечать как зонтик.",
        ),
        SurfaceCandidate(
            key="knowledge_a_plus_d",
            title="a+d",
            kind="specific",
            source_unit_key="unit_2",
            answer_scope="Дополненное знание a с добавлением d.",
            question_scope="Только вопросы про a с дополнением d.",
            exclusion_scope="Не отвечать на общие вопросы 1/2/A.",
        ),
        SurfaceCandidate(
            key="knowledge_b",
            title="b",
            kind="specific",
            source_unit_key="unit_1",
            answer_scope="Полное знание b.",
            question_scope="Только вопросы про b.",
            exclusion_scope="Не отвечать на общие вопросы 1/2/A.",
        ),
        SurfaceCandidate(
            key="knowledge_b_minus_e",
            title="b-e",
            kind="specific",
            source_unit_key="unit_2",
            answer_scope="Неполная версия знания b.",
            question_scope="Вопросы про b, но без части e.",
            exclusion_scope="Не публиковать как отдельное полное знание, если найдено полное b.",
        ),
        SurfaceCandidate(
            key="knowledge_c",
            title="c",
            kind="specific",
            source_unit_key="unit_1",
            answer_scope="Знание c.",
            question_scope="Только вопросы про c.",
            exclusion_scope="Не отвечать на общие вопросы.",
        ),
        SurfaceCandidate(
            key="knowledge_c_prime",
            title="c'",
            kind="specific",
            source_unit_key="unit_2",
            answer_scope="То же знание c, выраженное иначе.",
            question_scope="Только вопросы про c'.",
            exclusion_scope="Не отвечать на общие вопросы.",
        ),
        SurfaceCandidate(
            key="knowledge_g",
            title="g",
            kind="specific",
            source_unit_key="unit_1",
            answer_scope="Узкое знание g.",
            question_scope="Только вопросы про g.",
            exclusion_scope="Не отвечать на вопросы 1/2/A.",
        ),
        SurfaceCandidate(
            key="knowledge_j",
            title="j",
            kind="specific",
            source_unit_key="unit_a",
            answer_scope="Узкое знание j, добавленное через поздний мегазонтик A.",
            question_scope="Только вопросы про j.",
            exclusion_scope="Не отвечать на общие вопросы 2/A.",
        ),
    ]

    local_relations = [
        SurfaceRelation(
            parent_key="surface_1",
            child_key="knowledge_a",
            relation_type="umbrella_contains",
        ),
        SurfaceRelation(
            parent_key="surface_1",
            child_key="knowledge_b",
            relation_type="umbrella_contains",
        ),
        SurfaceRelation(
            parent_key="surface_1",
            child_key="knowledge_c",
            relation_type="umbrella_contains",
        ),
        SurfaceRelation(
            parent_key="surface_1",
            child_key="knowledge_g",
            relation_type="umbrella_contains",
        ),
        SurfaceRelation(
            parent_key="surface_2",
            child_key="knowledge_a_plus_d",
            relation_type="umbrella_contains",
        ),
        SurfaceRelation(
            parent_key="surface_2",
            child_key="knowledge_b_minus_e",
            relation_type="umbrella_contains",
        ),
        SurfaceRelation(
            parent_key="surface_2",
            child_key="knowledge_c_prime",
            relation_type="umbrella_contains",
        ),
        SurfaceRelation(
            parent_key="surface_a",
            child_key="surface_1",
            relation_type="umbrella_contains",
        ),
        SurfaceRelation(
            parent_key="surface_a",
            child_key="surface_2",
            relation_type="umbrella_contains",
        ),
        SurfaceRelation(
            parent_key="surface_2",
            child_key="knowledge_j",
            relation_type="umbrella_contains",
        ),
    ]

    same_surface_evidence = [
        ("knowledge_a", "knowledge_a_plus_d", "supplemented_by"),
        ("knowledge_b_minus_e", "knowledge_b", "incomplete_version_of"),
        ("knowledge_c", "knowledge_c_prime", "same_knowledge"),
    ]

    initial_questions = [
        QuestionOwnership(
            surface_key="surface_1",
            question="что входит в 1?",
            kind="overview",
        ),
        QuestionOwnership(
            surface_key="surface_2",
            question="что входит в 2?",
            kind="overview",
        ),
        QuestionOwnership(
            surface_key="surface_a",
            question="что такое A?",
            kind="overview",
        ),
        QuestionOwnership(
            surface_key="knowledge_a",
            question="что такое a?",
            kind="narrow",
        ),
        QuestionOwnership(
            surface_key="knowledge_a_plus_d",
            question="как a дополняется d?",
            kind="narrow",
        ),
        QuestionOwnership(
            surface_key="knowledge_b",
            question="что такое b?",
            kind="narrow",
        ),
        QuestionOwnership(
            surface_key="knowledge_b_minus_e",
            question="что известно про b без e?",
            kind="narrow",
        ),
        QuestionOwnership(
            surface_key="knowledge_c",
            question="что такое c?",
            kind="narrow",
        ),
        QuestionOwnership(
            surface_key="knowledge_c_prime",
            question="что такое c'?",
            kind="narrow",
        ),
        QuestionOwnership(
            surface_key="knowledge_g",
            question="что такое g?",
            kind="narrow",
        ),
        QuestionOwnership(
            surface_key="knowledge_j",
            question="что такое j?",
            kind="narrow",
        ),
    ]

    graph = reconcile_surface_graph(
        candidates=candidates,
        local_relations=local_relations,
        same_surface_evidence=same_surface_evidence,
        initial_questions=initial_questions,
    )

    assert graph.has_relation("surface_a", "surface_1", "umbrella_contains")
    assert graph.has_relation("surface_a", "surface_2", "umbrella_contains")

    assert graph.has_relation("surface_1", "knowledge_a_plus_d", "umbrella_contains")
    assert graph.has_relation("surface_1", "knowledge_b", "umbrella_contains")
    assert graph.has_relation("surface_1", "knowledge_c_merged", "umbrella_contains")
    assert graph.has_relation("surface_1", "knowledge_g", "umbrella_contains")

    assert graph.has_relation("surface_2", "knowledge_a_plus_d", "umbrella_contains")
    assert graph.has_relation("surface_2", "knowledge_b", "umbrella_contains")
    assert graph.has_relation("surface_2", "knowledge_c_merged", "umbrella_contains")
    assert graph.has_relation("surface_2", "knowledge_j", "umbrella_contains")

    assert graph.has_merged_surface(
        canonical_key="knowledge_a_plus_d",
        absorbed_keys={"knowledge_a"},
        merge_type="supplemented_knowledge",
    )
    assert graph.has_merged_surface(
        canonical_key="knowledge_b",
        absorbed_keys={"knowledge_b_minus_e"},
        merge_type="incomplete_evidence_absorbed",
    )
    assert graph.has_merged_surface(
        canonical_key="knowledge_c_merged",
        absorbed_keys={"knowledge_c", "knowledge_c_prime"},
        merge_type="same_knowledge",
    )

    assert graph.questions_for("surface_a").isdisjoint(
        graph.questions_for("surface_1")
        | graph.questions_for("surface_2")
        | graph.questions_for("knowledge_a_plus_d")
        | graph.questions_for("knowledge_b")
        | graph.questions_for("knowledge_c_merged")
        | graph.questions_for("knowledge_g")
        | graph.questions_for("knowledge_j")
    )
    assert graph.questions_for("surface_1").isdisjoint(
        graph.questions_for("knowledge_a_plus_d")
        | graph.questions_for("knowledge_b")
        | graph.questions_for("knowledge_c_merged")
        | graph.questions_for("knowledge_g")
    )
    assert graph.questions_for("surface_2").isdisjoint(
        graph.questions_for("knowledge_a_plus_d")
        | graph.questions_for("knowledge_b")
        | graph.questions_for("knowledge_c_merged")
        | graph.questions_for("knowledge_j")
    )

    assert graph.surface("surface_a").kind == "umbrella"
    assert graph.surface("surface_1").kind == "umbrella"
    assert graph.surface("surface_2").kind == "umbrella"

    assert graph.surface("knowledge_a_plus_d").kind in {"child", "specific"}
    assert graph.surface("knowledge_b").kind in {"child", "specific"}
    assert graph.surface("knowledge_c_merged").kind in {"child", "specific"}
    assert graph.surface("knowledge_g").kind in {"child", "specific"}
    assert graph.surface("knowledge_j").kind in {"child", "specific"}

    assert graph.surface("surface_2").answer_mentions("j")
    assert not graph.surface("surface_2").answers_narrow_question_about("j")
