from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_split_compiler_does_not_use_monolithic_source_units_prompt() -> None:
    source = (
        ROOT / "src/infrastructure/llm/knowledge_surface_split_compiler.py"
    ).read_text(encoding="utf-8")

    assert "for index, unit in enumerate(units)" in source
    assert "source_units=(unit,)" in source
    assert "source_units[:" not in source
    assert "source_unit_split_compilation" in source
    assert "Fallback relation between adjacent source-unit surfaces" in source


def test_quality_gated_compiler_uses_full_graph_pipeline() -> None:
    source = (
        ROOT / "src/infrastructure/llm/knowledge_surface_quality_gated_compiler.py"
    ).read_text(encoding="utf-8")

    assert "GroqFullKnowledgeSurfaceGraphCompiler" in source
    assert "GroqSplitKnowledgeSurfaceCompiler" not in source
    assert "class GroqQualityGatedKnowledgeSurfaceCompiler" in source


def test_full_graph_compiler_runs_all_required_stages() -> None:
    source = (
        ROOT / "src/infrastructure/llm/knowledge_surface_full_graph_compiler.py"
    ).read_text(encoding="utf-8")

    for needle in (
        "discover_surfaces_for_source_unit",
        "plan_local_relations",
        "synthesize_surface_answer",
        "assign_surface_questions",
        "_judge_global_relations",
        "_reassign_questions",
        "validate_faq_surface_graph_quality",
        "full_staged_surface_graph_v1",
    ):
        assert needle in source
