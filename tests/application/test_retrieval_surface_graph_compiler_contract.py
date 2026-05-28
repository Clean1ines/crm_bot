from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "src/agent/prompts"


def test_staged_surface_graph_compiler_port_declares_required_methods() -> None:
    source = (ROOT / "src/application/ports/knowledge_port.py").read_text(
        encoding="utf-8"
    )

    assert "class KnowledgeSurfaceGraphCompilerPort" in source
    for method_name in (
        "discover_surfaces_for_source_unit",
        "plan_local_relations",
        "synthesize_surface_answer",
        "assign_surface_questions",
        "judge_relation_cluster",
        "reconcile_global_graph",
    ):
        assert f"async def {method_name}" in source


def test_staged_surface_graph_prompts_are_split_by_compiler_stage() -> None:
    prompt_files = {
        "faq_surface_local_discovery.ru.txt": (
            "surface_candidates",
            "Не создавай одну гигантскую карточку",
        ),
        "faq_surface_local_relations.ru.txt": (
            "umbrella_contains",
            "broad_card_vacuum_risk",
        ),
        "faq_surface_answer_synthesis_v2.ru.txt": (
            "parent candidates",
            "child candidates",
            "sibling candidates",
            "umbrella отвечает только обзорно",
        ),
        "faq_surface_question_ownership_v2.ru.txt": (
            "owned_questions",
            "rejected_questions",
            "umbrella не может владеть child-specific questions",
        ),
        "faq_surface_global_relation_judge.ru.txt": (
            "needs_new_parent",
            "reparent_needed",
            "Не объединяй parent и child как duplicate",
        ),
        "faq_surface_question_reassignment.ru.txt": (
            "misplaced questions",
            "parent/umbrella не владеет вопросами детей",
        ),
    }

    for file_name, needles in prompt_files.items():
        source = (PROMPTS / file_name).read_text(encoding="utf-8")
        for needle in needles:
            assert needle in source


def test_legacy_surface_compiler_keeps_monolithic_method_outside_graph_port() -> None:
    graph_port_source = (ROOT / "src/application/ports/knowledge_port.py").read_text(
        encoding="utf-8"
    )
    graph_port_section = graph_port_source.split(
        "class KnowledgeSurfaceGraphCompilerPort", 1
    )[1].split("class KnowledgeSurfaceCompilerFactoryPort", 1)[0]

    assert "compile_surfaces" not in graph_port_section
    assert "source_units[:" not in graph_port_section
