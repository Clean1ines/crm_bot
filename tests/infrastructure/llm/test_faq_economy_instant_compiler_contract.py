from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
QUALITY = ROOT / "src/infrastructure/llm/knowledge_surface_quality_gated_compiler.py"
ECONOMY = ROOT / "src/infrastructure/llm/knowledge_surface_economy_instant.py"


def test_quality_compiler_keeps_wrapper_behavior() -> None:
    source = QUALITY.read_text(encoding="utf-8")

    assert "class GroqQualityGatedKnowledgeSurfaceCompiler(" in source
    assert "GroqEconomyInstantKnowledgeSurfaceGraphCompiler" in source
    assert "route_observability_snapshot" in source
    assert "callback_with_route_metrics" in source


def test_economy_compiler_contract_markers() -> None:
    source = ECONOMY.read_text(encoding="utf-8")

    assert "split_source_unit_for_instant" in source
    assert "set_cancel_check" in source
    assert "GroqFallbackExhaustedError" in source
    assert "GROQ_INSTANT_MODEL_ID" in source
    assert "ECONOMY_INSTANT_QUALITY_WARNING" in source
    assert "RetrievalSurfaceMergeDecision" in source
