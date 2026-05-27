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


def test_quality_gated_compiler_keeps_backward_compatible_import_name() -> None:
    source = (
        ROOT / "src/infrastructure/llm/knowledge_surface_quality_gated_compiler.py"
    ).read_text(encoding="utf-8")

    assert "GroqSplitKnowledgeSurfaceCompiler" in source
    assert "class GroqQualityGatedKnowledgeSurfaceCompiler" in source
